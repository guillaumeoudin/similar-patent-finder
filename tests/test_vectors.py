import pytest

from priorart.embeddings import e5_prefix
from priorart.vectors import load_vectors, save_vectors


def test_vectors_round_trip(tmp_path):
    ids = ["a:claim:1:0", "b:abstract:0:0"]
    vecs = [[0.5, -1.0, 2.0], [0.0, 0.25, 4.0]]
    save_vectors(tmp_path, ids, vecs, model="toy")
    got_ids, got_vecs, meta = load_vectors(tmp_path)
    assert got_ids == ids
    assert got_vecs == vecs  # these values are exact in 32 bit floats
    assert meta == {"model": "toy", "dim": 3, "count": 2}


def test_mismatched_lengths_are_refused(tmp_path):
    with pytest.raises(ValueError):
        save_vectors(tmp_path, ["a"], [[1.0], [2.0]], model="toy")


def test_truncated_file_is_detected(tmp_path):
    save_vectors(tmp_path, ["a", "b"], [[1.0, 2.0], [3.0, 4.0]], model="toy")
    path = tmp_path / "vectors.f32"
    path.write_bytes(path.read_bytes()[:-4])
    with pytest.raises(ValueError):
        load_vectors(tmp_path)


def test_e5_prefixes_only_for_e5_models():
    assert e5_prefix("intfloat/multilingual-e5-small", "query") == "query: "
    assert e5_prefix("intfloat/multilingual-e5-small", "document") == "passage: "
    assert e5_prefix("BAAI/bge-m3", "query") == ""
