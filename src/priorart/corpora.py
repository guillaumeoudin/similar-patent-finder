"""The collections the tool can search. Each one has its own PostgreSQL schema.

The list lives in corpora.json, next to this file: a label and a description, the language of
its patents (the web page lists the collections of the language it is shown in), the CPC group
the patents come from, and the file the patents are prepared into. Adding a collection means
adding an entry and running `priorart index --corpus <id>`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REGISTRY = Path(__file__).with_name("corpora.json")


@dataclass(frozen=True)
class Corpus:
    id: str
    lang: str  # language of the patents and of the text below: "en" or "fr"
    schema: str
    patents_file: str
    cpc: str
    period: tuple[int, int]
    evaluated: bool  # True only for the collection that the README measures
    label: str
    description: str
    placeholder: str
    examples: list
    abstain_below: dict | None = None  # per embedder, when the global cutoff does not fit


def load_corpora() -> list[Corpus]:
    items = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return [
        Corpus(
            id=i["id"],
            lang=i["lang"],
            schema=i["schema"],
            patents_file=i["patents_file"],
            cpc=i["cpc"],
            period=tuple(i["period"]),
            evaluated=i["evaluated"],
            label=i["label"],
            description=i["description"],
            placeholder=i["placeholder"],
            examples=i["examples"],
            abstain_below=i.get("abstain_below"),
        )
        for i in items
    ]


def get_corpus(corpus_id: str | None) -> Corpus:
    corpora = load_corpora()
    if corpus_id is None:
        return corpora[0]
    for c in corpora:
        if c.id == corpus_id:
            return c
    raise KeyError(f"unknown collection: {corpus_id}")
