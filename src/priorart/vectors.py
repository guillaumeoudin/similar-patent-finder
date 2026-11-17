"""Save and load embedding vectors as plain files.

Why: the open model can run on a different machine (one with a strong GPU) than the one
that hosts the database. That machine writes a folder with the vectors, the folder is
copied over, and `priorart index --vectors <folder>` loads it into the database.

Format, standard library only:
  meta.json       model name, dimension, number of vectors
  chunk_ids.json  list of chunk ids, in order
  vectors.f32     all vectors as 32 bit floats, one after the other
"""

from __future__ import annotations

import json
import sys
from array import array
from pathlib import Path


def save_vectors(
    folder: Path, chunk_ids: list[str], vectors: list[list[float]], model: str
) -> None:
    if len(chunk_ids) != len(vectors):
        raise ValueError("one vector per chunk id is required")
    dim = len(vectors[0]) if vectors else 0
    flat = array("f")
    for v in vectors:
        if len(v) != dim:
            raise ValueError("all vectors must have the same dimension")
        flat.extend(v)
    if sys.byteorder == "big":
        flat.byteswap()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "vectors.f32").write_bytes(flat.tobytes())
    (folder / "chunk_ids.json").write_text(json.dumps(chunk_ids))
    meta = {"model": model, "dim": dim, "count": len(chunk_ids)}
    (folder / "meta.json").write_text(json.dumps(meta))


def load_vectors(folder: Path) -> tuple[list[str], list[list[float]], dict]:
    meta = json.loads((folder / "meta.json").read_text())
    chunk_ids = json.loads((folder / "chunk_ids.json").read_text())
    flat = array("f")
    flat.frombytes((folder / "vectors.f32").read_bytes())
    if sys.byteorder == "big":
        flat.byteswap()
    dim, count = meta["dim"], meta["count"]
    if len(flat) != dim * count or len(chunk_ids) != count:
        raise ValueError("vector files are inconsistent (wrong size)")
    vectors = [list(flat[i * dim : (i + 1) * dim]) for i in range(count)]
    return chunk_ids, vectors, meta
