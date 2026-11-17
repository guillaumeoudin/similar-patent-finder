"""Split a patent into searchable chunks, one per section.

Sections kept in V1: the abstract (one chunk) and each claim (one chunk per claim,
split further only if the claim is very long). Every chunk keeps the patent id, the
section name and its position, so a search result can always be traced to its source.

Chunk text is never modified: later steps quote it word for word.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_CHARS = 2000


@dataclass(frozen=True)
class Chunk:
    patent_id: str
    section: str  # "abstract" or "claim"
    position: int  # claim number, or 0 for the abstract
    part: int  # 0 unless a long text was split
    text: str
    is_independent: bool = True

    @property
    def chunk_id(self) -> str:
        return f"{self.patent_id}:{self.section}:{self.position}:{self.part}"


def split_long_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Split text into pieces of at most max_chars, cutting after ';' or '.' when possible.

    Joining the pieces gives back the original text exactly.
    """
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    rest = text
    while len(rest) > max_chars:
        window = rest[:max_chars]
        cuts = [m.end() for m in re.finditer(r"[;.]\s", window)]
        cut = cuts[-1] if cuts and cuts[-1] > max_chars // 2 else max_chars
        pieces.append(rest[:cut])
        rest = rest[cut:]
    if rest:
        pieces.append(rest)
    return pieces


def chunk_patent(patent: dict, max_chars: int = MAX_CHARS) -> list[Chunk]:
    chunks: list[Chunk] = []
    pid = patent["patent_id"]

    abstract = (patent.get("abstract") or "").strip()
    if abstract:
        for part, piece in enumerate(split_long_text(abstract, max_chars)):
            chunks.append(Chunk(pid, "abstract", 0, part, piece))

    for claim in patent.get("claims", []):
        text = claim["text"].strip()
        if not text:
            continue
        independent = claim.get("dependent_on") is None
        for part, piece in enumerate(split_long_text(text, max_chars)):
            chunks.append(Chunk(pid, "claim", claim["number"], part, piece, independent))
    return chunks
