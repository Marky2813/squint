"""Map character spans in OCR text to pixel boxes."""

from squint.core.types import BBox, OcrLine, OcrWord

DEFAULT_PADDING = 3.0
# Where a match starts or ends mid-word, widen the cut by this many characters. Character
# positions inside a word are estimated (fonts are rarely monospaced), so err towards
# hiding a little extra rather than leaving an edge of the secret visible.
CUT_SLACK_CHARS = 1.0


def union(boxes: list[BBox]) -> BBox:
    left = min(b.x for b in boxes)
    top = min(b.y for b in boxes)
    right = max(b.x + b.width for b in boxes)
    bottom = max(b.y + b.height for b in boxes)
    return BBox(left, top, right - left, bottom - top)


def pad(box: BBox, padding: float) -> BBox:
    return BBox(
        box.x - padding,
        box.y - padding,
        box.width + 2 * padding,
        box.height + 2 * padding,
    )


def span_to_bbox(
    line: OcrLine, start: int, end: int, padding: float = DEFAULT_PADDING
) -> BBox | None:
    """Box covering text[start:end], or None if no word overlaps it.

    OCR boxes are per word, so a match inside a word ("KEY=sk_live_x") is located by
    character position within that word: the key stays readable, only the value is hidden.
    """
    hits = [
        _clip(w, start, end)
        for w in line.words
        if w.char_start < end and start < w.char_end
    ]
    if not hits:
        return None
    return pad(union(hits), padding)


def _clip(word: OcrWord, start: int, end: int) -> BBox:
    """The part of word's box holding characters [start, end), assuming even widths."""
    box = word.bbox
    length = word.char_end - word.char_start
    char_width = box.width / length
    first = max(start, word.char_start) - word.char_start
    last = min(end, word.char_end) - word.char_start
    if first > 0:
        first = max(0.0, first - CUT_SLACK_CHARS)
    if last < length:
        last = min(length, last + CUT_SLACK_CHARS)
    return BBox(
        box.x + first * char_width, box.y, (last - first) * char_width, box.height
    )
