"""Data types shared across the pipeline."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BBox:
    """Axis-aligned box in image pixels, origin top-left."""

    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class OcrWord:
    """A word within an OcrLine; char_start/char_end index into OcrLine.text."""

    char_start: int
    char_end: int
    bbox: BBox


@dataclass(frozen=True)
class OcrLine:
    text: str
    words: tuple[OcrWord, ...]


@dataclass(frozen=True)
class Candidate:
    """A regex match the classifier may judge. value is never logged."""

    id: int
    rule: str
    value: str
    context: str
