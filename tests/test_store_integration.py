"""Runs against a real PostgreSQL with pgvector (docker compose up -d). Skipped if unreachable."""

import os

import pytest

from priorart.chunking import Chunk

psycopg = pytest.importorskip("psycopg")

ADMIN_URL = os.environ.get(
    "TEST_ADMIN_URL", "postgresql://priorart:priorart@localhost:5432/priorart"
)
TEST_DB = "priorart_test"
TEST_URL = ADMIN_URL.rsplit("/", 1)[0] + "/" + TEST_DB


@pytest.fixture(scope="module")
def store():
    try:
        admin = psycopg.connect(ADMIN_URL, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("no PostgreSQL available")
    admin.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    admin.execute(f"CREATE DATABASE {TEST_DB}")
    from priorart.store import Store

    s = Store(TEST_URL, dim=3)
    s.reset()
    yield s
    admin.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")


def fill(store):
    for pid in ("1", "2", "3"):
        store.add_patent({"patent_id": pid, "title": f"Title {pid}", "date": "2020-01-01"})
    chunks = [
        Chunk("1", "claim", 1, 0, "A wireless charging coil with a ferrite shield"),
        Chunk("2", "claim", 1, 0, "A method of baking bread in a heated oven"),
        Chunk("3", "abstract", 0, 0, "Inductive power transfer using a flat coil"),
    ]
    vectors = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.9, 0.1, 0.0]]
    store.add_chunks(chunks, vectors)


def test_vector_search_orders_by_cosine_similarity(store):
    fill(store)
    rows = store.vector_search([1.0, 0.0, 0.0], limit=3)
    assert [r.patent_id for r in rows] == ["1", "3", "2"]
    assert rows[0].similarity == pytest.approx(1.0, abs=1e-6)
    assert rows[2].similarity == pytest.approx(0.0, abs=1e-6)


def test_vector_search_can_exclude_a_patent(store):
    fill(store)
    rows = store.vector_search([1.0, 0.0, 0.0], limit=3, exclude_patent_id="1")
    assert "1" not in [r.patent_id for r in rows]


def test_keyword_search_matches_any_word_and_ranks(store):
    fill(store)
    rows = store.keyword_search("wireless charging coil", limit=5)
    ids = [r.patent_id for r in rows]
    assert ids[0] == "1"
    assert "3" in ids  # shares only the word coil
    assert "2" not in ids


def test_keyword_search_uses_stemming(store):
    fill(store)
    assert [r.patent_id for r in store.keyword_search("charge", limit=5)] == ["1"]


def test_keyword_search_exclude_and_empty_query(store):
    fill(store)
    assert store.keyword_search("coil", 5, exclude_patent_id="1")[0].patent_id == "3"
    assert store.keyword_search("a an of", 5) == []


def test_adding_the_same_chunk_twice_is_harmless(store):
    fill(store)
    before = store.count_chunks()
    fill(store)
    assert store.count_chunks() == before


def test_patent_titles(store):
    fill(store)
    assert store.patent_titles(["1", "2"]) == {"1": "Title 1", "2": "Title 2"}
