"""Map character spans in OCR text to pixel boxes."""

from squint.core.types import BBox, OcrLine

DEFAULT_PADDING = 3.0


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
    """Box covering every word that overlaps text[start:end], or None if none do.

    Over-redacts to whole words: a match inside "KEY=sk_live_x" covers the whole token.
    """
    hits = [w.bbox for w in line.words if w.char_start < end and start < w.char_end]
    if not hits:
        return None
    return pad(union(hits), padding)
