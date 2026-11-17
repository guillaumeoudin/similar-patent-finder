"""Pick a small random collection of patents from one CPC group, for the web demo.

    python corpora/select_corpus.py --cpc A47J31/ --size 450 --seed 7 --out corpora/coffee_ids.json

Reads the raw PatentsView files in data/raw (not versioned). Writes patent numbers only, so the
list can be committed. Then prepare the texts and index them:

    python -m priorart.ingest --ids corpora/coffee_ids.json \\
        --out data/processed/patents_coffee.jsonl
    priorart index --corpus coffee

These collections only illustrate the tool. They have no examiner based answer key and are not
part of the evaluation in the README.
"""

import argparse
import csv
import io
import json
import random
import zipfile
from pathlib import Path

RAW = Path("data/raw")
WINDOW = ("2015-01-01", "2025-12-31")


def rows(name: str):
    z = zipfile.ZipFile(RAW / f"{name}.tsv.zip")
    f = io.TextIOWrapper(z.open(z.namelist()[0]), encoding="utf-8", errors="replace", newline="")
    reader = csv.reader(f, delimiter="\t", quotechar='"')
    return next(reader), reader


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cpc", required=True, help="CPC group prefix, for example A47J31/")
    parser.add_argument("--size", type=int, default=450)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    header, reader = rows("g_cpc_current")
    group_i, patent_i = header.index("cpc_group"), header.index("patent_id")
    domain = {r[patent_i] for r in reader if r[group_i].startswith(args.cpc)}
    print(f"patents in CPC {args.cpc}: {len(domain)}")

    header, reader = rows("g_patent")
    date_i = header.index("patent_date")
    kept = sorted(r[0] for r in reader if r[0] in domain and WINDOW[0] <= r[date_i] <= WINDOW[1])
    print(f"granted {WINDOW[0][:4]} to {WINDOW[1][:4]}: {len(kept)}")

    random.Random(args.seed).shuffle(kept)
    chosen = sorted(kept[: args.size])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {"cpc": args.cpc, "window": WINDOW, "seed": args.seed, "corpus": chosen}, indent=1
        ),
        encoding="utf-8",
    )
    print(f"wrote {len(chosen)} patent numbers to {args.out}")


if __name__ == "__main__":
    main()
