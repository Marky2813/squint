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


def test_span_covering_whole_word_returns_that_word_padded():
    assert span_to_bbox(LINE, 9, 24, padding=0) == BBox(95, 20, 150, 12)
    assert span_to_bbox(LINE, 9, 24, padding=2) == BBox(93, 18, 154, 16)


def test_span_inside_word_covers_only_its_characters_plus_slack():
    # word [9,24) is 150px for 15 chars: 10px each; chars 3..11 widen to 2..12
    assert span_to_bbox(LINE, 12, 20, padding=0) == BBox(115, 20, 100, 12)


def test_value_after_key_in_one_token_leaves_key_visible():
    line = OcrLine('KEY="secret"', (OcrWord(0, 12, BBox(0, 0, 120, 10)),))
    box = span_to_bbox(line, 5, 11, padding=0)  # secret
    assert box == BBox(40, 0, 80, 10)  # from the opening quote to the end
    assert box.x > 30  # "KEY" (0-30px) stays readable


def test_span_across_words_clips_both_ends():
    assert span_to_bbox(LINE, 4, 20, padding=0) == BBox(40, 20, 175, 12)


def test_span_touching_word_edge_does_not_include_neighbour():
    assert span_to_bbox(LINE, 24, 25, padding=0) is None
    assert span_to_bbox(LINE, 8, 9, padding=0) is None


def test_span_with_no_words_returns_none():
    assert span_to_bbox(OcrLine(text="x", words=()), 0, 1) is None
