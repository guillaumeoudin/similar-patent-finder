from priorart.chunking import Chunk, chunk_patent, split_long_text
from priorart.ingest import dedupe_claims, parse_dependency


def make_patent():
    return {
        "patent_id": "1234567",
        "abstract": "A wireless charger with a coil.",
        "claims": [
            {"number": 1, "text": "1. A charger comprising a coil.", "dependent_on": None},
            {
                "number": 2,
                "text": "2. The charger of claim 1, wherein the coil is round.",
                "dependent_on": 1,
            },
        ],
    }


def test_one_chunk_per_section_with_metadata():
    chunks = chunk_patent(make_patent())
    positions = [(c.section, c.position) for c in chunks]
    assert positions == [("abstract", 0), ("claim", 1), ("claim", 2)]
    assert all(c.patent_id == "1234567" for c in chunks)


def test_dependent_claims_are_flagged():
    chunks = chunk_patent(make_patent())
    assert [c.is_independent for c in chunks if c.section == "claim"] == [True, False]


def test_text_is_kept_exactly():
    patent = make_patent()
    chunks = chunk_patent(patent)
    assert chunks[1].text == patent["claims"][0]["text"]


def test_missing_abstract_and_empty_claims_are_skipped():
    patent = {"patent_id": "9", "claims": [{"number": 1, "text": "  ", "dependent_on": None}]}
    assert chunk_patent(patent) == []


def test_long_claim_is_split_without_losing_a_character():
    text = ("A device comprising a part; " * 200).strip()
    pieces = split_long_text(text, max_chars=300)
    assert len(pieces) > 1
    assert all(len(p) <= 300 for p in pieces)
    assert "".join(pieces) == text


def test_split_chunks_have_distinct_ids():
    patent = {
        "patent_id": "5",
        "claims": [{"number": 1, "text": "x; " * 1500, "dependent_on": None}],
    }
    ids = [c.chunk_id for c in chunk_patent(patent, max_chars=500)]
    assert len(ids) == len(set(ids)) > 1


def test_parse_dependency():
    assert parse_dependency("claim 12") == 12
    assert parse_dependency("") is None
    assert parse_dependency("garbage") is None


def test_chunk_id_format():
    assert Chunk("1", "claim", 3, 0, "t").chunk_id == "1:claim:3:0"


def test_dedupe_claims_drops_exact_repeats_only():
    a = {"number": 1, "text": "1. A thing.", "dependent_on": None}
    b = {"number": 2, "text": "2. The thing of claim 1.", "dependent_on": 1}
    different = {"number": 1, "text": "1. Another thing.", "dependent_on": None}
    assert dedupe_claims([a, b, dict(a), different]) == [a, b, different]
