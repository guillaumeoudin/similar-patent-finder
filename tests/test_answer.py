import json

from priorart.answer import (
    Item,
    answer_query,
    check_items,
    normalize,
    parse_items,
    verify_excerpt,
)
from priorart.search import Hit, SearchResult
from priorart.store import ChunkRow

SOURCE = (
    "A wireless power transmitter comprising a coil\nand a controller, wherein the\ncoil is flat."
)


def test_normalize_collapses_whitespace_quotes_and_case():
    assert normalize("Hello\n  “World” ") == 'hello "world"'


def test_verbatim_excerpt_is_verified_even_across_line_breaks():
    assert verify_excerpt("a coil and a controller, wherein the coil is flat", SOURCE)


def test_paraphrase_is_rejected():
    assert not verify_excerpt("a flat coil with a controller unit inside", SOURCE)


def test_altered_word_is_rejected():
    assert not verify_excerpt("a wireless power transmitter comprising a magnet", SOURCE)


def test_very_short_excerpt_is_rejected():
    assert not verify_excerpt("a coil", SOURCE)


def make_result():
    chunk = ChunkRow("7:claim:1:0", "7", "claim", 1, SOURCE)
    return SearchResult([Hit("7", 0.03, [chunk])], best_similarity=0.8, abstained=False)


def model_output(excerpt, patent_id="7", passage_id="7:claim:1:0"):
    item = {"patent_id": patent_id, "passage_id": passage_id, "excerpt": excerpt,
            "close": "same coil", "different": "none"}  # fmt: skip
    return json.dumps({"items": [item]})


class FakeAnswerer:
    def __init__(self, output):
        self.output = output

    def generate(self, system, user):
        assert "Invention description" in user
        return self.output, 100, 50


def test_good_answer_is_reliable():
    out = model_output("a coil and a controller, wherein the coil is flat")
    ans = answer_query("q", make_result(), FakeAnswerer(out))
    assert ans.reliable and len(ans.items) == 1 and not ans.rejected
    assert ans.input_tokens == 100


def test_invented_excerpt_is_rejected_and_flags_the_answer():
    out = model_output("a quantum coil that charges phones through walls")
    ans = answer_query("q", make_result(), FakeAnswerer(out))
    assert not ans.reliable and len(ans.rejected) == 1 and not ans.items


def test_excerpt_attributed_to_the_wrong_patent_is_rejected():
    out = model_output("a coil and a controller, wherein the coil is flat", patent_id="8")
    ans = answer_query("q", make_result(), FakeAnswerer(out))
    assert not ans.reliable


def test_unknown_passage_id_is_rejected():
    items = [Item("7", "7:claim:9:0", "a coil and a controller, wherein", "", "")]
    good, bad = check_items(items, {"7:claim:1:0": SOURCE})
    assert not good and len(bad) == 1


def test_invalid_json_flags_the_answer():
    ans = answer_query("q", make_result(), FakeAnswerer("sorry, I cannot do that"))
    assert not ans.reliable and not ans.items


def test_json_inside_code_fence_is_parsed():
    out = "```json\n" + model_output("x" * 20) + "\n```"
    assert len(parse_items(out)) == 1


def test_empty_list_is_a_valid_answer():
    ans = answer_query("q", make_result(), FakeAnswerer('{"items": []}'))
    assert ans.reliable and not ans.items


def test_abstention_skips_the_model():
    class Boom:
        def generate(self, system, user):
            raise AssertionError("must not be called")

    result = SearchResult([], best_similarity=0.1, abstained=True)
    assert answer_query("q", result, Boom()).abstained
