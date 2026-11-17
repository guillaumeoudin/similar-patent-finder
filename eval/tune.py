"""Tune the search settings on the DEVELOPMENT set only.

1. Fetch the candidate chunks once per query (100 by vector, 100 by keyword).
2. Replay the fusion offline for many settings, in three modes: vector only, keyword only,
   hybrid. This shows what each part brings.
3. Pick the abstention threshold from the best cosine similarity of each query: development
   queries (should be answered) against the first ten negatives (should not be).

The test set is never touched here. Results are written to eval/results/.

Usage: python eval/tune.py
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from priorart.config import load_settings
from priorart.embeddings import make_embedder
from priorart.metrics import mean, recall_at_k, reciprocal_rank
from priorart.search import fuse
from priorart.store import Store

SPLIT = Path("eval/dataset/split.json")
PATENTS = Path("data/processed/patents.jsonl")
NEGATIVES = Path("eval/negative_queries.txt")
RESULTS = Path("eval/results")
FETCH = 100
RRF_KS = [10, 30, 60, 100]
CANDIDATES = [20, 50, 100]


def query_text(patent: dict) -> str:
    first = next((c["text"] for c in patent["claims"] if c["number"] == 1), "")
    return f"{patent['abstract']}\n\n{first}"


def main() -> None:
    settings = load_settings()
    split = json.loads(SPLIT.read_text())
    patents = {}
    with PATENTS.open(encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            patents[p["patent_id"]] = p
    embedder = make_embedder(settings)
    store = Store(settings.database_url, settings.dim)

    cache = {}
    for qid in split["dev"]:
        text = query_text(patents[qid])
        vec = embedder.embed([text], kind="query")[0]
        cache[qid] = (
            store.vector_search(vec, FETCH, qid),
            store.keyword_search(text, FETCH, qid),
        )

    rows = []
    for mode in ("vector", "keyword", "hybrid"):
        for k in RRF_KS if mode == "hybrid" else [60]:
            for cand in CANDIDATES:
                r5, r10, rr = [], [], []
                for qid, expected in split["dev"].items():
                    bv, bk = cache[qid]
                    hits = fuse(bv[:cand], bk[:cand], k, 10, mode=mode)
                    ranked = [h.patent_id for h in hits]
                    rel = set(expected)
                    r5.append(recall_at_k(ranked, rel, 5))
                    r10.append(recall_at_k(ranked, rel, 10))
                    rr.append(reciprocal_rank(ranked, rel))
                row = {"mode": mode, "rrf_k": k, "candidates": cand}
                row.update({"recall@5": mean(r5), "recall@10": mean(r10), "mrr": mean(rr)})
                rows.append(row)

    print(f"{'mode':8} {'k':>4} {'cand':>5} {'R@5':>6} {'R@10':>6} {'MRR':>6}")
    for r in rows:
        print(f"{r['mode']:8} {r['rrf_k']:>4} {r['candidates']:>5} "
              f"{r['recall@5']:6.3f} {r['recall@10']:6.3f} {r['mrr']:6.3f}")  # fmt: skip

    # abstention threshold
    pos = sorted(max((c.similarity or 0.0) for c in cache[q][0]) for q in cache)
    neg_texts = [n for n in NEGATIVES.read_text().splitlines() if n.strip()][:10]
    neg = sorted(
        max(
            (c.similarity or 0.0)
            for c in store.vector_search(embedder.embed([t], kind="query")[0], 20)
        )
        for t in neg_texts
    )
    # Candidate thresholds sit halfway between neighbouring observed similarities.
    observed = sorted(set(pos + neg))
    cuts = [(x + y) / 2 for x, y in zip(observed, observed[1:], strict=False)]
    scored = []
    for t in cuts:
        # balanced accuracy: share of positives answered and share of negatives abstained
        bal = (sum(s >= t for s in pos) / len(pos) + sum(s < t for s in neg) / len(neg)) / 2
        scored.append((bal, t))
    top_bal = max(b for b, _ in scored)
    plateau = [t for b, t in scored if b == top_bal]
    best = (top_bal, plateau[len(plateau) // 2])  # middle of the best range, not its edge
    print("\nbest cosine similarity, development queries:", [round(s, 3) for s in pos])
    print("best cosine similarity, tuning negatives:   ", [round(s, 3) for s in neg])
    print(f"threshold with best balanced accuracy: {best[1]:.4f} (balanced accuracy {best[0]:.2f})")

    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS / f"tuning_dev_{stamp}.json"
    report = {
        "embedder": embedder.name,
        "rows": rows,
        "positive_similarities": pos,
        "negative_similarities": neg,
        "threshold": best[1],
        "balanced_accuracy": best[0],
    }
    out.write_text(json.dumps(report, indent=1))
    print(f"written {out}")


if __name__ == "__main__":
    main()
