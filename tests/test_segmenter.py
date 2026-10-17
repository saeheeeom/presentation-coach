import pytest

from backend.llm import parse_groups
from backend.segmenter import (
    build_segments,
    count_words,
    split_rule_based,
    split_sentences,
    target_seconds,
)

SCRIPT = """Good morning, everyone. Thank you.

Today I want to show you how our new model works. It is three times faster than the baseline. Dr. Smith ran the original experiments, e.g. the ablations, at the U.S. lab.

Let me start with the problem. Most practice tools only report raw acoustic numbers. Nobody can act on those."""


def test_count_words_handles_contractions_and_hyphens():
    assert count_words("It's a state-of-the-art model, v2.5!") == 5


def test_target_seconds_from_wpm():
    assert target_seconds(" ".join(["word"] * 140), wpm=140) == 60.0


def test_split_sentences_skips_abbreviations():
    sentences = split_sentences("Dr. Smith ran it, e.g. the ablations, at the U.S. lab. Then we stopped.")
    assert sentences == ["Dr. Smith ran it, e.g. the ablations, at the U.S. lab.", "Then we stopped."]


def test_split_sentences_keeps_closing_quotes():
    assert split_sentences('He said "stop." Then left.') == ['He said "stop."', "Then left."]


def test_short_sentences_are_merged():
    segments = split_rule_based(SCRIPT, mode="sentence")
    assert segments[0] == "Good morning, everyone. Thank you."


def test_paragraph_mode():
    assert len(split_rule_based(SCRIPT, mode="paragraph")) == 3


def test_auto_mode_respects_max_words_and_paragraphs():
    segments = split_rule_based(SCRIPT, mode="auto", max_words=20)
    assert all(count_words(s) <= 25 for s in segments)
    # no segment crosses the paragraph boundary
    assert not any("Thank you. Today" in s for s in segments)
    # text is preserved exactly (modulo whitespace)
    assert " ".join(segments).split() == SCRIPT.split()


def test_build_segments_drops_empty():
    segs = build_segments(["Hello there friends.", "  "], wpm=60)
    assert len(segs) == 1 and segs[0].word_count == 3 and segs[0].target_seconds == 3.0


PARAS = [["A one.", "A two."], ["B one."]]


def test_parse_groups_valid():
    assert parse_groups("Sure! [[1, 2], [3]]", PARAS) == ["A one. A two.", "B one."]


@pytest.mark.parametrize(
    "reply",
    ["no json here", "[[1], [3]]", "[[2, 1], [3]]", "[[1], [2, 3]]", "[[1, 2, 3]]"],
)
def test_parse_groups_rejects_bad_output(reply):
    with pytest.raises(ValueError):
        parse_groups(reply, PARAS)
