"""OCR lines -> regex candidates -> Gemma verdicts -> findings with boxes."""

import re
from dataclasses import dataclass
from typing import Protocol

from squint.core.candidates import SENSITIVE, extract
from squint.core.classify import Verdicts
from squint.core.geometry import DEFAULT_PADDING, pad, span_to_bbox, union
from squint.core.types import BBox, Candidate, OcrLine


class Classifier(Protocol):
    def judge_all(self, candidates: list[Candidate]) -> Verdicts: ...


@dataclass(frozen=True)
class Finding:
    id: int
    rule: str
    tier: str
    value: str
    bbox: BBox | None
    flagged: bool


@dataclass(frozen=True)
class Analysis:
    findings: tuple[Finding, ...]
    classifier_offline: bool

    @property
    def flagged(self) -> list[Finding]:
        return [f for f in self.findings if f.flagged]


def mask(value: str) -> str:
    """Safe-to-display preview of a matched value."""
    if len(value) <= 10:
        return "•" * len(value)
    return f"{value[:4]}…{value[-3:]}"


# Characters that end a token: whitespace, quotes and closing punctuation.
_TOKEN_END = set(" \t\"'`,;)]}>")
# OCR sometimes reads a "." inside a long token as a space; the rest looks like this.
_CONTINUATION = re.compile(r"[A-Za-z0-9_\-.=+/]{16,}")
_SPLIT_PRONE = {"jwt", "bearer"}


def _looks_encoded(word: str) -> bool:
    """base64-ish: mixed case or digits (ordinary long words are neither)."""
    has_upper = any(c.isupper() for c in word)
    has_lower = any(c.islower() for c in word)
    return (has_upper and has_lower) or (any(c.isdigit() for c in word) and has_lower)


def secret_span(text: str, start: int, end: int, rule: str) -> tuple[int, int]:
    """Widen a match to cover the whole secret on screen, not just what the regex read.

    An OCR misread mid-token stops the regex early and would leave the tail visible, so
    the span always runs to the end of its token. Tokens OCR tends to split (JWTs, bearer
    tokens) also absorb a following word that looks like more of the same token.
    """
    while end < len(text) and text[end] not in _TOKEN_END:
        end += 1
    if rule in _SPLIT_PRONE:
        while end < len(text) and text[end] == " ":
            nxt = _CONTINUATION.match(text, end + 1)
            if not nxt or not _looks_encoded(nxt.group()):
                break
            end = nxt.end()
    return start, end


def _box(line: OcrLine, start: int, end: int, rule: str = "") -> BBox | None:
    start, end = secret_span(line.text, start, end, rule)
    box = span_to_bbox(line, start, end)
    if box is None and line.words:
        # No word overlaps the span (unexpected OCR offsets): cover the whole line.
        return pad(union([w.bbox for w in line.words]), DEFAULT_PADDING)
    return box


def analyze(lines: list[OcrLine], classifier: Classifier) -> Analysis:
    matches = extract(lines)
    candidates = [
        Candidate(i, m.rule, m.value, m.context)
        for i, m in enumerate(matches)
        if m.tier != SENSITIVE
    ]
    verdicts = classifier.judge_all(candidates)
    findings = tuple(
        Finding(
            id=i,
            rule=m.rule,
            tier=m.tier,
            value=m.value,
            bbox=_box(lines[m.line], m.start, m.end, m.rule),
            flagged=m.tier == SENSITIVE or verdicts.sensitive.get(i, True),
        )
        for i, m in enumerate(matches)
    )
    return Analysis(findings, verdicts.classifier_offline)
