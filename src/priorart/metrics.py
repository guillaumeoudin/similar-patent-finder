"""Evaluation metrics. All inputs are plain lists of patent ids."""

from __future__ import annotations


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    """Share of the expected documents found in the first k results."""
    if not relevant:
        return 0.0
    return len(set(ranked[:k]) & relevant) / len(relevant)


def reciprocal_rank(ranked: list[str], relevant: set[str]) -> float:
    """1 / rank of the first expected document, or 0 if none is found."""
    for rank, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / rank
    return 0.0


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
