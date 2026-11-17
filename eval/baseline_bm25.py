"""Keyword-only baseline (BM25), in pure Python. No database, no API, no cost.

It answers one question: how far does plain keyword search get on this evaluation?
The hybrid search must beat this number to justify its extra moving parts.

Same chunks, same queries and same patent-level aggregation as run_eval.py. The test set
is deliberately not offered here: it is run once, at the end, with the real pipeline.

Usage: python eval/baseline_bm25.py
"""

from __future__ import annotations

import json
import math
import re
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from priorart.chunking import chunk_patent
from priorart.metrics import mean, recall_at_k, reciprocal_rank
from priorart.store import STOPWORDS

K1, B = 1.2, 0.75
SPLIT = Path("eval/dataset/split.json")
PATENTS = Path("data/processed/patents.jsonl")
RESULTS = Path("eval/results")


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) >= 3 and t not in STOPWORDS]


def query_text(patent: dict) -> str:
    first = next((c["text"] for c in patent["claims"] if c["number"] == 1), "")
    return f"{patent['abstract']}\n\n{first}"


def main() -> None:
    split = json.loads(SPLIT.read_text())
    patents = {}
    with PATENTS.open(encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            patents[p["patent_id"]] = p

    chunks = [c for p in patents.values() for c in chunk_patent(p)]
    docs = [Counter(tokens(c.text)) for c in chunks]
    lengths = [sum(d.values()) for d in docs]
    avg_len = sum(lengths) / len(lengths)
    postings: dict[str, list[int]] = defaultdict(list)
    for i, d in enumerate(docs):
        for term in d:
            postings[term].append(i)
    n = len(docs)
    idf = {t: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in postings.items()}

    def search(text: str, exclude: str) -> list[str]:
        scores: dict[int, float] = defaultdict(float)
        for term in set(tokens(text)):
            for i in postings.get(term, []):
                tf = docs[i][term]
                norm = tf * (K1 + 1) / (tf + K1 * (1 - B + B * lengths[i] / avg_len))
                scores[i] += idf[term] * norm
        best: dict[str, float] = {}
        for i, s in scores.items():
            pid = chunks[i].patent_id
            if pid != exclude and s > best.get(pid, 0.0):
                best[pid] = s
        return [p for p, _ in sorted(best.items(), key=lambda t: t[1], reverse=True)][:10]

    r5, r10, rr, secs, records = [], [], [], [], []
    for qid, expected in split["dev"].items():
        start = time.perf_counter()
        ranked = search(query_text(patents[qid]), exclude=qid)
        secs.append(time.perf_counter() - start)
        rel = set(expected)
        r5.append(recall_at_k(ranked, rel, 5))
        r10.append(recall_at_k(ranked, rel, 10))
        rr.append(reciprocal_rank(ranked, rel))
        records.append({"type": "query", "query_id": qid, "expected": expected, "ranked": ranked})

    summary = {
        "type": "summary", "system": "bm25_keyword_only", "set": "dev", "queries": len(r5),
        "recall@5": mean(r5), "recall@10": mean(r10), "mrr": mean(rr),
        "mean_seconds_per_query": mean(secs), "chunks": n,
    }  # fmt: skip
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS / f"baseline_bm25_dev_{stamp}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for rec in [{"type": "config", "k1": K1, "b": B, "time": stamp}, *records, summary]:
            f.write(json.dumps(rec) + "\n")
    print(json.dumps(summary, indent=2))
    print(f"log written to {out}")


if __name__ == "__main__":
    main()
