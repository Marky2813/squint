from squint.core.classify import Verdicts
from squint.core.pipeline import analyze, mask
from squint.core.types import BBox, OcrLine, OcrWord

FAKE_AWS = "AKIA" + "FAKE" * 4


class StubClassifier:
    def __init__(self, verdict=False, offline=False):
        self.verdict = verdict
        self.offline = offline
        self.seen = []

    def judge_all(self, candidates):
        self.seen.extend(candidates)
        return Verdicts({c.id: self.verdict for c in candidates}, self.offline)


def line(text, *spans):
    return OcrLine(
        text,
        tuple(OcrWord(s, e, BBox(10 * s, 0, 10 * (e - s), 12)) for s, e in spans),
    )


def test_sensitive_matches_skip_the_classifier_and_are_flagged():
    stub = StubClassifier()
    result = analyze([line(f"id {FAKE_AWS}", (0, 2), (3, 23))], stub)
    assert stub.seen == []
    [finding] = result.findings
    assert finding.flagged
    assert finding.rule == "aws_key"
    assert finding.bbox == BBox(27, -3, 206, 18)


def test_ambiguous_matches_follow_the_classifier():
    text = "DB_PASSWORD=hunter2-FAKE"
    stub = StubClassifier(verdict=False)
    result = analyze([line(text, (0, len(text)))], stub)
    assert [c.value for c in stub.seen] == ["hunter2-FAKE"]
    assert result.flagged == []
    assert len(result.findings) == 1


def test_offline_classifier_is_reported():
    text = "DB_PASSWORD=hunter2-FAKE"
    result = analyze([line(text, (0, len(text)))], StubClassifier(True, offline=True))
    assert result.classifier_offline
    assert result.findings[0].flagged


def test_missing_verdict_counts_as_flagged():
    class Empty:
        def judge_all(self, candidates):
            return Verdicts({}, False)

    text = "DB_PASSWORD=hunter2-FAKE"
    assert analyze([line(text, (0, len(text)))], Empty()).findings[0].flagged


def test_span_without_overlapping_word_falls_back_to_whole_line():
    result = analyze([line(f"id {FAKE_AWS}", (0, 2))], StubClassifier())
    assert result.findings[0].bbox == BBox(-3, -3, 26, 18)


def test_line_without_words_has_no_box():
    result = analyze([OcrLine(f"id {FAKE_AWS}", ())], StubClassifier())
    assert result.findings[0].bbox is None


def test_clean_text_has_no_findings():
    result = analyze([line("hello world", (0, 5), (6, 11))], StubClassifier())
    assert result.findings == ()


def test_mask_hides_middle_of_long_values_and_all_of_short_ones():
    assert mask("sk_live_FAKE1234FAKE") == "sk_l…AKE"
    assert mask("hunter2") == "•••••••"
