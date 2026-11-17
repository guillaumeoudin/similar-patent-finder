"""Select the evaluation sub-corpus from the raw PatentsView tables.

Reads the raw files in data/raw (not versioned) and writes eval/dataset/split.json,
which holds patent numbers only (no patent text), so it can be committed.

Steps:
1. Keep granted patents with a CPC group under H02J50 and a grant date in the window.
2. Keep citations made by an examiner where both patents are in that set.
3. Pick query patents with 3 to 8 such citations (the expected answers).
4. Split them into a development set and a test set (fixed random seed).
5. Corpus = queries + their expected answers + random distractors from the same set.
"""

import csv
import io
import json
import random
import zipfile
from collections import defaultdict
from pathlib import Path

RAW = Path("data/raw")
OUT = Path("eval/dataset/split.json")
CPC_PREFIX = "H02J50/"
WINDOW = ("2015-01-01", "2025-12-31")
MIN_GOLD, MAX_GOLD = 3, 8
N_DEV, N_TEST = 20, 50
CORPUS_SIZE = 500
SEED = 42


def rows(name: str):
    """Stream a PatentsView table from its zip file, yielding (header, rows)."""
    z = zipfile.ZipFile(RAW / f"{name}.tsv.zip")
    f = io.TextIOWrapper(z.open(z.namelist()[0]), encoding="utf-8", errors="replace", newline="")
    reader = csv.reader(f, delimiter="\t", quotechar='"')
    return next(reader), reader


def main() -> None:
    h, r = rows("g_cpc_current")
    gi, pi = h.index("cpc_group"), h.index("patent_id")
    domain = {row[pi] for row in r if row[gi].startswith(CPC_PREFIX)}

    h, r = rows("g_patent")
    di = h.index("patent_date")
    in_window = {row[0] for row in r if row[0] in domain and WINDOW[0] <= row[di] <= WINDOW[1]}
    grant_year = {}
    h, r = rows("g_patent")
    for row in r:
        if row[0] in in_window:
            grant_year[row[0]] = row[di][:4]

    h, r = rows("g_us_patent_citation")
    pi, ci, ki = h.index("patent_id"), h.index("citation_patent_id"), h.index("citation_category")
    gold: dict[str, set[str]] = defaultdict(set)
    for row in r:
        if row[ki] == "cited by examiner" and row[pi] in in_window and row[ci] in in_window:
            gold[row[pi]].add(row[ci])

    candidates = sorted(p for p, g in gold.items() if MIN_GOLD <= len(g) <= MAX_GOLD)
    rng = random.Random(SEED)
    queries = rng.sample(candidates, N_DEV + N_TEST)
    dev, test = queries[:N_DEV], queries[N_DEV:]

    corpus = set(queries)
    for q in queries:
        corpus |= gold[q]
    distractors = sorted(in_window - corpus)
    rng.shuffle(distractors)
    corpus |= set(distractors[: max(0, CORPUS_SIZE - len(corpus))])

    split = {
        "config": {
            "cpc_prefix": CPC_PREFIX,
            "window": WINDOW,
            "seed": SEED,
            "min_gold": MIN_GOLD,
            "max_gold": MAX_GOLD,
        },
        "dev": {q: sorted(gold[q]) for q in dev},
        "test": {q: sorted(gold[q]) for q in test},
        "corpus": sorted(corpus),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(split, indent=1))

    years = defaultdict(int)
    for p in corpus:
        years[grant_year[p]] += 1
    print("patents in domain and window:", len(in_window))
    print("query candidates:", len(candidates))
    print("corpus size:", len(corpus))
    print("corpus by grant year:", dict(sorted(years.items())))


if __name__ == "__main__":
    main()
