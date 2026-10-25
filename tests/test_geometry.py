from squint.core.geometry import pad, span_to_bbox, union
from squint.core.types import BBox, OcrLine, OcrWord

# "API_KEY= sk_live_FAKE123 end" -> words at [0,8), [9,24), [25,28)
LINE = OcrLine(
    text="API_KEY= sk_live_FAKE123 end",
    words=(
        OcrWord(0, 8, BBox(10, 20, 80, 12)),
        OcrWord(9, 24, BBox(95, 20, 150, 12)),
        OcrWord(25, 28, BBox(250, 21, 30, 11)),
    ),
)


def test_union_covers_all_boxes():
    assert union([BBox(10, 20, 5, 5), BBox(0, 22, 4, 10)]) == BBox(0, 20, 15, 12)


def test_pad_grows_every_side():
    assert pad(BBox(10, 10, 20, 5), 2) == BBox(8, 8, 24, 9)


def test_span_inside_one_word_returns_that_word_padded():
    assert span_to_bbox(LINE, 9, 24, padding=0) == BBox(95, 20, 150, 12)
    assert span_to_bbox(LINE, 12, 20, padding=2) == BBox(93, 18, 154, 16)


def test_span_across_words_returns_union():
    assert span_to_bbox(LINE, 4, 20, padding=0) == BBox(10, 20, 235, 12)


def test_span_touching_word_edge_does_not_include_neighbour():
    assert span_to_bbox(LINE, 24, 25, padding=0) is None
    assert span_to_bbox(LINE, 8, 9, padding=0) is None


def test_span_with_no_words_returns_none():
    assert span_to_bbox(OcrLine(text="x", words=()), 0, 1) is None
