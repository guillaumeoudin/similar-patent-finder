"""PostgreSQL storage with pgvector (vectors) and full text search (keywords).

One database does both jobs. Chunks live in one table with a vector column and a
generated tsvector column, each with its own index.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from priorart.chunking import Chunk

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "has",
    "have", "had", "not", "but", "can", "its", "than", "then", "when", "which", "wherein",
    "said", "one", "two", "each", "may", "such", "into", "also", "any", "all", "use",
}  # fmt: skip


def schema_sql(dim: int) -> str:
    return f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS patents (
    patent_id text PRIMARY KEY,
    title text,
    grant_date date
);
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id text PRIMARY KEY,
    patent_id text NOT NULL REFERENCES patents(patent_id),
    section text NOT NULL,
    position integer NOT NULL,
    part integer NOT NULL,
    is_independent boolean NOT NULL,
    text text NOT NULL,
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    embedding vector({int(dim)})
);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);
"""


def or_tsquery(text: str, max_terms: int = 1000) -> str:
    """Build an OR query from free text, for example 'coil | charging | power'.

    A plain AND query is too strict for a long invention description: no chunk would
    contain every word. With OR, the ranking function decides which chunks match best.
    Every term is kept: cutting the query to its first terms lost about a fifth of the recall
    on the development set.
    """
    seen: list[str] = []
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        if len(token) >= 3 and token not in STOPWORDS and token not in seen:
            seen.append(token)
    return " | ".join(seen[:max_terms])


@dataclass(frozen=True)
class ChunkRow:
    chunk_id: str
    patent_id: str
    section: str
    position: int
    text: str
    similarity: float | None = None  # cosine similarity, set by vector search only


class Store:
    def __init__(self, database_url: str, dim: int):
        import psycopg
        from pgvector.psycopg import register_vector

        self._conn = psycopg.connect(database_url, autocommit=True)
        self._conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(self._conn)
        self.dim = dim

    def init_schema(self) -> None:
        self._conn.execute(schema_sql(self.dim))

    def reset(self) -> None:
        self._conn.execute("DROP TABLE IF EXISTS chunks, patents CASCADE")
        self.init_schema()

    def add_patent(self, patent: dict) -> None:
        self._conn.execute(
            "INSERT INTO patents (patent_id, title, grant_date) VALUES (%s, %s, %s) "
            "ON CONFLICT (patent_id) DO NOTHING",
            (patent["patent_id"], patent.get("title"), patent.get("date")),
        )

    def add_chunks(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        with self._conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO chunks (chunk_id, patent_id, section, position, part,"
                " is_independent, text, embedding) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (chunk_id) DO NOTHING",
                [
                    (c.chunk_id, c.patent_id, c.section, c.position, c.part,
                     c.is_independent, c.text, v)
                    for c, v in zip(chunks, vectors, strict=True)
                ],
            )  # fmt: skip

    def chunk_ids(self) -> set[str]:
        return {r[0] for r in self._conn.execute("SELECT chunk_id FROM chunks").fetchall()}

    def count_chunks(self) -> int:
        return self._conn.execute("SELECT count(*) FROM chunks").fetchone()[0]

    def vector_search(
        self, vector: list[float], limit: int, exclude_patent_id: str | None = None
    ) -> list[ChunkRow]:
        rows = self._conn.execute(
            "SELECT chunk_id, patent_id, section, position, text,"
            " 1 - (embedding <=> %s::vector) AS sim FROM chunks "
            "WHERE (%s::text IS NULL OR patent_id <> %s) "
            "ORDER BY embedding <=> %s::vector LIMIT %s",
            (vector, exclude_patent_id, exclude_patent_id, vector, limit),
        ).fetchall()
        return [ChunkRow(r[0], r[1], r[2], r[3], r[4], float(r[5])) for r in rows]

    def keyword_search(
        self, query: str, limit: int, exclude_patent_id: str | None = None
    ) -> list[ChunkRow]:
        tsq = or_tsquery(query)
        if not tsq:
            return []
        rows = self._conn.execute(
            "SELECT chunk_id, patent_id, section, position, text FROM chunks "
            "WHERE tsv @@ to_tsquery('english', %s) "
            "AND (%s::text IS NULL OR patent_id <> %s) "
            "ORDER BY ts_rank(tsv, to_tsquery('english', %s), 1) DESC LIMIT %s",
            (tsq, exclude_patent_id, exclude_patent_id, tsq, limit),
        ).fetchall()
        return [ChunkRow(*r) for r in rows]

    def patent_titles(self, ids: list[str]) -> dict[str, str]:
        rows = self._conn.execute(
            "SELECT patent_id, title FROM patents WHERE patent_id = ANY(%s)", (ids,)
        ).fetchall()
        return {r[0]: r[1] for r in rows}
