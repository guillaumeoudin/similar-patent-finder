import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from priorart import api  # noqa: E402
from priorart.store import ChunkRow  # noqa: E402

PASSAGE = "A wireless charging pad comprising a transmit coil and a metal object detector."


class FakeEmbedder:
    name = "fake"
    dim = 2

    def embed(self, texts, kind="document"):
        return [[1.0, 0.0] for _ in texts]


class FakeStore:
    def vector_search(self, vector, limit, exclude_patent_id=None):
        return [ChunkRow("7:claim:1:0", "7", "claim", 1, PASSAGE, 0.9)]

    def keyword_search(self, query, limit, exclude_patent_id=None):
        return []

    def patent_titles(self, ids):
        return {i: f"Title {i}" for i in ids}


class FakeAnswerer:
    def __init__(self, excerpt):
        self.excerpt = excerpt

    def generate(self, system, user):
        item = {"patent_id": "7", "passage_id": "7:claim:1:0", "excerpt": self.excerpt,
                "close": "same coil", "different": "no detector"}  # fmt: skip
        return json.dumps({"items": [item]}), 5, 5


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "get_engine", lambda: (FakeEmbedder(), FakeStore()))
    return TestClient(api.app)


QUERY = {"query": "a charging pad that detects metal objects on its surface"}


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_page_is_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Prior Art Finder" in resp.text


def test_search_returns_titles_and_passages(client):
    body = client.post("/search", json=QUERY).json()
    assert body["abstained"] is False
    hit = body["hits"][0]
    assert hit["patent_id"] == "7" and hit["title"] == "Title 7"
    assert hit["passages"][0]["text"] == PASSAGE
    assert "not legal advice" in body["disclaimer"]


def test_short_query_is_refused(client):
    assert client.post("/search", json={"query": "coil"}).status_code == 422


def test_answer_with_verified_quote(client, monkeypatch):
    monkeypatch.setattr(
        api, "get_answerer", lambda: FakeAnswerer("a transmit coil and a metal object")
    )
    body = client.post("/answer", json=QUERY).json()
    assert body["reliable"] is True
    assert body["items"][0]["verified"] is True and not body["rejected"]


def test_answer_with_invented_quote_is_flagged(client, monkeypatch):
    monkeypatch.setattr(
        api, "get_answerer", lambda: FakeAnswerer("a magic coil that charges through walls")
    )
    body = client.post("/answer", json=QUERY).json()
    assert body["reliable"] is False
    assert body["rejected"][0]["verified"] is False and not body["items"]


def test_backend_down_gives_503(monkeypatch):
    def boom():
        raise RuntimeError("MISTRAL_API_KEY is not set")

    monkeypatch.setattr(api, "get_engine", boom)
    resp = TestClient(api.app).post("/search", json=QUERY)
    assert resp.status_code == 503
    assert "MISTRAL_API_KEY" in resp.json()["detail"]
