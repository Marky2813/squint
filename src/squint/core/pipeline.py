"""OCR lines -> regex candidates -> Gemma verdicts -> findings with boxes."""

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


def _box(line: OcrLine, start: int, end: int) -> BBox | None:
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
            bbox=_box(lines[m.line], m.start, m.end),
            flagged=m.tier == SENSITIVE or verdicts.sensitive.get(i, True),
        )
        for i, m in enumerate(matches)
    )
    return Analysis(findings, verdicts.classifier_offline)
