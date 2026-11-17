"""Run the evaluation and write a JSON Lines log in eval/results/.

Query for a patent = its abstract plus its first claim (its cited references are never
part of the text). The patent itself is excluded from the results. The expected answers
are the references its examiner cited that are in the corpus (see build_dataset.py).

The development set is for tuning. The test set must be run once, at the end, with --final.
Twenty descriptions of things that are not in the corpus (eval/negative_queries.txt) check
that the tool abstains. The first ten (clearly off-topic) are used to tune the threshold. The
last ten (electrical devices that are not wireless power) are held out and only reported.

Usage:
    python eval/run_eval.py --set dev
    python eval/run_eval.py --set test --final
    add --answers to also generate and verify cited answers (costs API calls)
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from priorart.answer import answer_query, make_answerer
from priorart.config import load_settings
from priorart.embeddings import make_embedder
from priorart.metrics import mean, recall_at_k, reciprocal_rank
from priorart.search import hybrid_search
from priorart.store import Store

PATENTS = Path("data/processed/patents.jsonl")
SPLIT = Path("eval/dataset/split.json")
NEGATIVES = Path("eval/negative_queries.txt")
RESULTS = Path("eval/results")


def query_text(patent: dict) -> str:
    first = next((c["text"] for c in patent["claims"] if c["number"] == 1), "")
    return f"{patent['abstract']}\n\n{first}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=["dev", "test"], required=True)
    parser.add_argument("--final", action="store_true", help="required to run the test set")
    parser.add_argument("--answers", action="store_true", help="also run the answer step")
    args = parser.parse_args()
    if args.set == "test" and not args.final:
        parser.error("the test set is run once, at the end: add --final")

    settings = load_settings()
    split = json.loads(SPLIT.read_text())
    patents = {}
    with PATENTS.open(encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            patents[p["patent_id"]] = p

    embedder = make_embedder(settings)
    store = Store(settings.database_url, settings.dim)
    answerer = make_answerer(settings) if args.answers else None

    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS / f"run_{args.set}_{stamp}.jsonl"
    log = out.open("w", encoding="utf-8")

    def write(record: dict) -> None:
        log.write(json.dumps(record, ensure_ascii=False) + "\n")

    write({"type": "config", "set": args.set, "answers": args.answers, "time": stamp,
           "settings": {k: v for k, v in settings.__dict__.items() if "key" not in k},
           "embedder": embedder.name})  # fmt: skip

    r5, r10, rr, latencies = [], [], [], []
    abstained_pos = verified = total_items = unreliable = 0
    for query_id, expected in split[args.set].items():
        text = query_text(patents[query_id])
        start = time.perf_counter()
        result = hybrid_search(store, embedder, text, settings, exclude_patent_id=query_id)
        ranked = [h.patent_id for h in result.hits]
        record = {
            "type": "query", "query_id": query_id, "expected": expected, "ranked": ranked,
            "best_similarity": result.best_similarity, "abstained": result.abstained,
        }  # fmt: skip
        if answerer is not None:
            ans = answer_query(text, result, answerer)
            record["answer"] = {
                "reliable": ans.reliable, "verified": len(ans.items),
                "rejected": len(ans.rejected),
                "tokens_in": ans.input_tokens, "tokens_out": ans.output_tokens,
            }  # fmt: skip
            verified += len(ans.items)
            total_items += len(ans.items) + len(ans.rejected)
            unreliable += not ans.reliable
        record["seconds"] = time.perf_counter() - start
        latencies.append(record["seconds"])
        rel = set(expected)
        r5.append(recall_at_k(ranked, rel, 5))
        r10.append(recall_at_k(ranked, rel, 10))
        rr.append(reciprocal_rank(ranked, rel))
        abstained_pos += result.abstained
        write(record)

    abstained_neg = 0
    negatives = [n for n in NEGATIVES.read_text().splitlines() if n.strip()][10:]
    for text in negatives:
        res = hybrid_search(store, embedder, text, settings)
        abstained_neg += res.abstained
        write({"type": "negative", "best_similarity": res.best_similarity,
               "abstained": res.abstained})  # fmt: skip

    n = len(r5)
    summary = {
        "type": "summary", "set": args.set, "queries": n,
        "recall@5": mean(r5), "recall@10": mean(r10), "mrr": mean(rr),
        "abstention_rate_on_real_queries": abstained_pos / n,
        "abstention_rate_on_off_topic": abstained_neg / max(1, len(negatives)),
        "citation_verified_rate": (verified / total_items) if total_items else None,
        "unreliable_answers": unreliable if answerer else None,
        "mean_seconds_per_query": mean(latencies),
        "embedder_tokens_used": getattr(embedder, "tokens_used", 0),
    }  # fmt: skip
    write(summary)
    log.close()
    print(json.dumps(summary, indent=2))
    print(f"log written to {out}")


if __name__ == "__main__":
    main()
