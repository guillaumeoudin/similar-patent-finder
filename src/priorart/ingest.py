"""Turn the raw PatentsView tables into one clean record per patent.

Only the patents listed in eval/dataset/split.json are kept. The output is a
JSON Lines file (data/processed/patents.jsonl), one patent per line:

    {"patent_id", "title", "date", "abstract",
     "claims": [{"number", "text", "dependent_on"}]}

Claim text is kept exactly as published. It is never rewritten, because the answer
step later checks that every quoted excerpt exists word for word in the source.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

csv.field_size_limit(10_000_000)  # some claims are very long


def read_table(zip_path: Path) -> Iterator[dict[str, str]]:
    """Stream a PatentsView .tsv.zip file as dictionaries (one per row)."""
    with zipfile.ZipFile(zip_path) as z, z.open(z.namelist()[0]) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
        yield from csv.DictReader(text, delimiter="\t", quotechar='"')


def parse_dependency(value: str) -> int | None:
    """'claim 12' gives 12. An empty value (independent claim) gives None."""
    value = value.strip()
    if not value.startswith("claim "):
        return None
    try:
        return int(value.split()[1])
    except (IndexError, ValueError):
        return None


def load_corpus_ids(split_path: Path) -> set[str]:
    return set(json.loads(split_path.read_text())["corpus"])


def build_patents(raw_dir: Path, ids: set[str]) -> dict[str, dict]:
    patents: dict[str, dict] = {pid: {"patent_id": pid, "claims": []} for pid in ids}

    for row in read_table(raw_dir / "g_patent.tsv.zip"):
        if row["patent_id"] in patents:
            patents[row["patent_id"]]["title"] = row["patent_title"]
            patents[row["patent_id"]]["date"] = row["patent_date"]

    for row in read_table(raw_dir / "g_patent_abstract.tsv.zip"):
        if row["patent_id"] in patents:
            patents[row["patent_id"]]["abstract"] = row["patent_abstract"]

    claims: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for path in sorted(raw_dir.glob("g_claims_*.tsv.zip")):
        for row in read_table(path):
            if row["patent_id"] in patents:
                claim = {
                    "number": int(row["claim_number"]),
                    "text": row["claim_text"],
                    "dependent_on": parse_dependency(row["dependent"]),
                }
                claims[row["patent_id"]].append((int(row["claim_sequence"]), claim))
    for pid, items in claims.items():
        patents[pid]["claims"] = [c for _, c in sorted(items, key=lambda t: t[0])]
    return patents


def main() -> None:
    root = Path(".")
    ids = load_corpus_ids(root / "eval/dataset/split.json")
    patents = build_patents(root / "data/raw", ids)
    out = root / "data/processed/patents.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for pid in sorted(patents):
            f.write(json.dumps(patents[pid], ensure_ascii=False) + "\n")

    missing_abstract = [p for p in patents.values() if not p.get("abstract")]
    missing_claims = [p for p in patents.values() if not p["claims"]]
    print(f"patents written: {len(patents)} -> {out}")
    print(f"without abstract: {len(missing_abstract)}; without claims: {len(missing_claims)}")


if __name__ == "__main__":
    main()
