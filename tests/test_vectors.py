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


def test_voyage_embedder_sends_input_type_retries_and_orders(monkeypatch):
    import httpx

    from priorart.config import Settings
    from priorart.embeddings import VoyageEmbedder

    calls = []
    answers = [(429, {}), (200, {"data": [{"index": 1, "embedding": [2.0]},
                                         {"index": 0, "embedding": [1.0]}],
                                 "usage": {"total_tokens": 9}})]  # fmt: skip

    class FakeResponse:
        def __init__(self, status, body):
            self.status_code, self._body, self.headers = status, body, {"retry-after": "1"}

        def json(self):
            return self._body

        def raise_for_status(self):
            assert self.status_code == 200

    class FakeClient:
        def __init__(self, *a, **k): ...
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers, json):
            calls.append(json)
            return FakeResponse(*answers[len(calls) - 1])

    monkeypatch.setattr(httpx, "Client", FakeClient)
    emb = VoyageEmbedder(Settings(voyage_api_key="k"))
    emb._sleep = lambda s: None
    assert emb.embed(["a", "b"], kind="query") == [[1.0], [2.0]]
    assert len(calls) == 2 and calls[0]["input_type"] == "query"
    assert emb.tokens_used == 9


def test_voyage_embedder_needs_a_key():
    import pytest

    from priorart.config import Settings
    from priorart.embeddings import VoyageEmbedder

    with pytest.raises(RuntimeError, match="VOYAGE_API_KEY"):
        VoyageEmbedder(Settings())
