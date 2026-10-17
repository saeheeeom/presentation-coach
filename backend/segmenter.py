"""Split a presentation script into practice segments.

Segments are built from whole sentences so the original wording is never
altered. The rule-based splitter is always available; an optional local LLM
(see llm.py) can choose the grouping instead, and its output is validated
before use.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_WPM = 140
DEFAULT_MAX_WORDS = 45  # ~20s at 140 wpm: short enough that a restart is cheap
MIN_SENTENCE_WORDS = 6  # shorter sentences are merged with a neighbor

_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "e.g",
    "i.e", "u.s", "u.k", "fig", "no", "approx", "dept", "inc", "ltd", "co",
}
_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’\-.][A-Za-z0-9]+)*")
_SENTENCE_END_RE = re.compile(r"([.!?]+[\"'”’)\]]*)\s+")


@dataclass
class Segment:
    text: str
    word_count: int
    target_seconds: float


def count_words(text: str) -> int:
    return len(_WORD_RE.findall(text))


def target_seconds(text: str, wpm: float = DEFAULT_WPM) -> float:
    return round(count_words(text) / wpm * 60, 1)


def split_paragraphs(script: str) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", script.strip())
    return [" ".join(p.split()) for p in paragraphs if p.strip()]


def split_sentences(paragraph: str) -> list[str]:
    """Split on sentence-final punctuation, skipping common abbreviations."""
    sentences: list[str] = []
    start = 0
    for match in _SENTENCE_END_RE.finditer(paragraph):
        end = match.end(1)
        last_token = paragraph[start:end].split()[-1].rstrip(".!?\"'”’)]").lower()
        if match.group(1).startswith(".") and last_token in _ABBREVIATIONS:
            continue
        sentences.append(paragraph[start:end].strip())
        start = match.end()
    tail = paragraph[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def _merge_short(sentences: list[str]) -> list[str]:
    """Attach very short sentences ("Thank you.") to the following one."""
    merged: list[str] = []
    carry = ""
    for sentence in sentences:
        text = f"{carry} {sentence}".strip()
        if count_words(text) < MIN_SENTENCE_WORDS:
            carry = text
            continue
        merged.append(text)
        carry = ""
    if carry:
        if merged:
            merged[-1] = f"{merged[-1]} {carry}"
        else:
            merged.append(carry)
    return merged


def _group(sentences: list[str], max_words: int) -> list[str]:
    groups: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        candidate = current + [sentence]
        if current and count_words(" ".join(candidate)) > max_words:
            groups.append(" ".join(current))
            current = [sentence]
        else:
            current = candidate
    if current:
        groups.append(" ".join(current))
    return groups


def split_rule_based(script: str, mode: str = "auto", max_words: int = DEFAULT_MAX_WORDS) -> list[str]:
    """Return segment texts.

    mode="sentence": roughly one sentence per segment (tiny ones merged).
    mode="paragraph": one paragraph per segment.
    mode="auto": sentences grouped within each paragraph up to max_words.
    """
    segments: list[str] = []
    for paragraph in split_paragraphs(script):
        if mode == "paragraph":
            segments.append(paragraph)
            continue
        sentences = _merge_short(split_sentences(paragraph))
        if mode == "sentence":
            segments.extend(sentences)
        else:
            segments.extend(_group(sentences, max_words))
    return segments


def sentence_units(script: str) -> list[list[str]]:
    """Sentences per paragraph, as fed to the LLM segmenter."""
    return [split_sentences(p) for p in split_paragraphs(script)]


def build_segments(texts: list[str], wpm: float = DEFAULT_WPM) -> list[Segment]:
    return [
        Segment(text=t, word_count=count_words(t), target_seconds=target_seconds(t, wpm))
        for t in (t.strip() for t in texts)
        if t
    ]
