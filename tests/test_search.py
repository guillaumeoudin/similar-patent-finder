from priorart.config import Settings
from priorart.metrics import mean, recall_at_k, reciprocal_rank
from priorart.search import hybrid_search, rrf
from priorart.store import ChunkRow, or_tsquery


def test_rrf_rewards_items_found_in_both_rankings():
    scores = rrf([["a", "b", "c"], ["c", "a", "d"]], k=60)
    assert scores["a"] > scores["b"]
    assert scores["a"] > scores["d"]
    assert scores["c"] > scores["b"]


def test_rrf_matches_the_formula():
    scores = rrf([["a"], ["a"]], k=10)
    assert abs(scores["a"] - 2 / 11) < 1e-12


def test_rrf_empty():
    assert rrf([[], []]) == {}


def test_or_tsquery_drops_stopwords_short_words_and_duplicates():
    q = or_tsquery("The coil and the coil, a 5 mm charging-pad!")
    assert q == "coil | charging | pad"


def test_or_tsquery_empty_text():
    assert or_tsquery("a an of") == ""


class FakeEmbedder:
    name = "fake"
    dim = 2

    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


class FakeStore:
    def __init__(self, by_vector, by_keyword):
        self.by_vector, self.by_keyword = by_vector, by_keyword
        self.excluded = None

    def vector_search(self, vector, limit, exclude_patent_id=None):
        self.excluded = exclude_patent_id
        return self.by_vector

    def keyword_search(self, query, limit, exclude_patent_id=None):
        return self.by_keyword


def row(chunk_id, patent_id, sim=None):
    return ChunkRow(chunk_id, patent_id, "claim", 1, "text", sim)


def test_hybrid_search_groups_chunks_by_patent_and_ranks():
    vec = [row("1:claim:1:0", "1", 0.9), row("2:claim:1:0", "2", 0.8)]
    kw = [row("2:claim:1:0", "2"), row("2:claim:2:0", "2"), row("3:claim:1:0", "3")]
    result = hybrid_search(FakeStore(vec, kw), FakeEmbedder(), "q", Settings(), "99")
    ids = [h.patent_id for h in result.hits]
    assert ids[0] == "2"  # found by both rankings
    assert set(ids) == {"1", "2", "3"}
    assert len(result.hits[0].chunks) == 2
    assert result.best_similarity == 0.9
    assert not result.abstained


def test_hybrid_search_passes_the_excluded_patent_to_the_store():
    store = FakeStore([], [])
    hybrid_search(store, FakeEmbedder(), "q", Settings(), exclude_patent_id="42")
    assert store.excluded == "42"


def test_abstains_when_best_similarity_is_below_threshold():
    vec = [row("1:claim:1:0", "1", 0.30)]
    settings = Settings(abstain_below=0.5)
    result = hybrid_search(FakeStore(vec, []), FakeEmbedder(), "q", settings)
    assert result.abstained


def test_top_k_limits_patents():
    vec = [row(f"{i}:claim:1:0", str(i), 0.9) for i in range(30)]
    result = hybrid_search(FakeStore(vec, []), FakeEmbedder(), "q", Settings(top_k=5))
    assert len(result.hits) == 5


def test_metrics():
    ranked = ["x", "a", "y", "b"]
    assert recall_at_k(ranked, {"a", "b"}, 2) == 0.5
    assert recall_at_k(ranked, {"a", "b"}, 10) == 1.0
    assert recall_at_k(ranked, set(), 5) == 0.0
    assert reciprocal_rank(ranked, {"b", "a"}) == 0.5
    assert reciprocal_rank(ranked, {"zzz"}) == 0.0
    assert mean([1.0, 0.0]) == 0.5
    assert mean([]) == 0.0
