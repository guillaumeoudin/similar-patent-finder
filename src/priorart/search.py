"""Hybrid search: keyword ranking and vector ranking, merged with reciprocal rank fusion.

Reciprocal rank fusion (RRF) gives each chunk the score 1/(k + rank) in each ranking and
adds them up. It needs no score calibration between the two rankings, which is why it is
the simple, robust choice here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from priorart.config import Settings
from priorart.embeddings import Embedder
from priorart.store import ChunkRow


def rrf(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    """Fuse several ranked lists of ids into one score per id."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return scores


class SearchStore(Protocol):
    def vector_search(
        self, vector: list[float], limit: int, exclude_patent_id: str | None = None
    ) -> list[ChunkRow]: ...

    def keyword_search(
        self, query: str, limit: int, exclude_patent_id: str | None = None
    ) -> list[ChunkRow]: ...


@dataclass
class Hit:
    patent_id: str
    score: float  # best fused chunk score for this patent
    chunks: list[ChunkRow] = field(default_factory=list)  # best chunks first


@dataclass
class SearchResult:
    hits: list[Hit]
    best_similarity: float  # best cosine similarity among vector candidates
    abstained: bool


def fuse(
    by_vector: list[ChunkRow],
    by_keyword: list[ChunkRow],
    rrf_k: int,
    top_k: int,
    max_chunks_per_patent: int = 3,
    mode: str = "hybrid",
) -> list[Hit]:
    """Merge the two chunk rankings and group the result by patent.

    mode "vector" or "keyword" keeps only one ranking. It exists to measure each part alone.
    """
    if mode == "vector":
        by_keyword = []
    elif mode == "keyword":
        by_vector = []
    elif mode != "hybrid":
        raise ValueError(f"unknown mode: {mode}")

    rows = {r.chunk_id: r for r in by_vector + by_keyword}
    rankings = [[r.chunk_id for r in by_vector], [r.chunk_id for r in by_keyword]]
    fused = rrf(rankings, rrf_k)

    per_patent: dict[str, list[tuple[float, ChunkRow]]] = {}
    for chunk_id, score in fused.items():
        row = rows[chunk_id]
        per_patent.setdefault(row.patent_id, []).append((score, row))

    hits = []
    for patent_id, scored in per_patent.items():
        scored.sort(key=lambda t: t[0], reverse=True)
        hits.append(
            Hit(patent_id, scored[0][0], [row for _, row in scored[:max_chunks_per_patent]])
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]


def hybrid_search(
    store: SearchStore,
    embedder: Embedder,
    query: str,
    settings: Settings,
    exclude_patent_id: str | None = None,
    max_chunks_per_patent: int = 3,
    mode: str = "hybrid",
) -> SearchResult:
    vector = embedder.embed([query], kind="query")[0]
    by_vector = store.vector_search(vector, settings.candidates, exclude_patent_id)
    by_keyword = store.keyword_search(query, settings.candidates, exclude_patent_id)
    hits = fuse(by_vector, by_keyword, settings.rrf_k, settings.top_k, max_chunks_per_patent, mode)
    best_sim = max((r.similarity or 0.0 for r in by_vector), default=0.0)
    return SearchResult(hits, best_sim, abstained=best_sim < settings.abstain_below)
