import base64
import json

import pytest

from squint.core.candidates import (
    AMBIGUOUS,
    SENSITIVE,
    extract,
    is_benign,
    jwt_header_valid,
    luhn_valid,
    shannon_entropy,
)
from squint.core.types import OcrLine

# Synthetic values only. Built from obviously fake pieces so no scanner mistakes them for real keys.
FAKE_AWS = "AKIA" + "FAKE" * 4
FAKE_GHP = "ghp_" + "FAKE0" * 7 + "x"
FAKE_STRIPE = "sk_live_" + "FAKE1234" * 2
FAKE_SLACK = "xoxb-" + "1234-FAKE-" * 2
FAKE_GOOGLE = "AIza" + "FAKE_fake-" * 4
FAKE_JWT_HEADER = (
    base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
)
FAKE_JWT = f"{FAKE_JWT_HEADER}.eyJmYWtlIjp0cnVlfQ.FAKEsig"
TEST_CARD = "4242 4242 4242 4242"  # Stripe's public test number, Luhn-valid


def lines(*texts):
    return [OcrLine(text=t, words=()) for t in texts]


def only(text):
    found = extract(lines(text))
    assert len(found) == 1, found
    return found[0]


@pytest.mark.parametrize(
    "text, rule, value",
    [
        (
            "-----BEGIN OPENSSH PRIVATE KEY-----",
            "private_key",
            "-----BEGIN OPENSSH PRIVATE KEY-----",
        ),
        (f"aws_id {FAKE_AWS}", "aws_key", FAKE_AWS),
        (f"gh {FAKE_GHP}", "github_token", FAKE_GHP),
        (f"key {FAKE_STRIPE}", "stripe_key", FAKE_STRIPE),
        (f"slack {FAKE_SLACK}", "slack_token", FAKE_SLACK),
        (f"g {FAKE_GOOGLE}", "google_api_key", FAKE_GOOGLE),
        (f"jwt {FAKE_JWT}", "jwt", FAKE_JWT),
        (
            "postgres://admin:FAKEpw99@db.internal:5432/app",
            "url_credentials",
            "FAKEpw99",
        ),
        (
            "Authorization: Bearer dGhpc2lzZmFrZXNlY3JldA",
            "bearer",
            "dGhpc2lzZmFrZXNlY3JldA",
        ),
        (f"card {TEST_CARD}", "card", TEST_CARD),
    ],
)
def test_sensitive_rules(text, rule, value):
    match = only(text)
    assert (match.rule, match.tier, match.value) == (rule, SENSITIVE, value)
    assert text[match.start : match.end] == value


@pytest.mark.parametrize(
    "text, rule, value",
    [
        ("DB_PASSWORD=hunter2-FAKE", "assignment", "hunter2-FAKE"),
        ("  password: Tr0ub4dor&3-FAKE", "assignment", "Tr0ub4dor&3-FAKE"),
        ('"api_key": "FAKEkey77"', "assignment", "FAKEkey77"),
        ("reach me at jane.doe.fake@gmail.com", "email", "jane.doe.fake@gmail.com"),
        ("call +1 415 555 0134 tonight", "phone", "+1 415 555 0134"),
        (
            "blob Zq8vR2mX7kLp4Tn9Wb3Yc6Hd1Fs5Gj0A",
            "high_entropy",
            "Zq8vR2mX7kLp4Tn9Wb3Yc6Hd1Fs5Gj0A",
        ),
    ],
)
def test_ambiguous_rules(text, rule, value):
    match = only(text)
    assert (match.rule, match.tier, match.value) == (rule, AMBIGUOUS, value)


@pytest.mark.parametrize(
    "text",
    [
        "password=changeme",
        'api_key = "<YOUR_API_KEY>"',
        "token: xxxxxxxx",
        "secret=${SECRET}",
        "From: GitHub <noreply@github.com>",
        "Questions? support@example.com",
        "contact jane@example.org",
        "commit 3f44648a1b2c9d0e7f6a5b4c3d2e1f0a9b8c7d6e",
        "digest sha256:9b1f2e7c4a6d8e0f1a3b5c7d9e2f4a6b8c0d1e3f5a7b9c1d3e5f7a9b1c3d5e7f",
        "request_id: 550e8400-e29b-41d4-a716-446655440000",
        "Released 2026-10-25 (v3.12.4)",
        "card 4242 4242 4242 4241",
        "OllamaClassifierWarmUpPrimesEverySlot",
        "see https://github.com/FAKEorg/FAKErepo2026/blob/main/src",
        "/Users/fake/projects/squint2026/src/core",
        "jwt eyJub3Rqc29u.eyJmYWtlIjp0cnVlfQ.sig",
    ],
)
def test_benign_text_yields_nothing(text):
    assert extract(lines(text)) == []


def test_weak_numeric_password_is_not_treated_as_placeholder():
    assert only("password: 123456").value == "123456"


def test_bearer_beats_high_entropy_for_same_span():
    match = only("Authorization: Bearer dGhpc2lzZmFrZXNlY3JldGtleTEyMzQ1Ng")
    assert match.rule == "bearer"


def test_vendor_token_beats_assignment_and_entropy():
    match = only(f"STRIPE_KEY={FAKE_STRIPE}")
    assert match.rule == "stripe_key"
    assert match.tier == SENSITIVE


def test_matches_record_line_index_and_context():
    found = extract(
        lines("first line", "DB_PASSWORD=hunter2-FAKE", "third line", "fourth")
    )
    [match] = found
    assert match.line == 1
    assert match.context == "first line\nDB_PASSWORD=hunter2-FAKE\nthird line"


def test_context_is_capped():
    found = extract(lines("a" * 300, "DB_PASSWORD=hunter2-FAKE"))
    assert len(found[0].context) == 200


def test_multiple_matches_on_one_line():
    found = extract(lines(f"{FAKE_AWS} and jane.doe.fake@gmail.com"))
    assert [m.rule for m in found] == ["aws_key", "email"]


def test_luhn_valid():
    assert luhn_valid("4242424242424242")
    assert not luhn_valid("4242424242424241")


def test_shannon_entropy():
    assert shannon_entropy("aaaa") == 0
    assert shannon_entropy("abcd") == 2


def test_jwt_header_valid():
    assert jwt_header_valid(FAKE_JWT)
    assert not jwt_header_valid("eyJub3Rqc29u.x.y")


def test_is_benign_placeholder_for_any_rule():
    assert is_benign("assignment", "<TOKEN>", "token: <TOKEN>", 7)
    assert not is_benign("assignment", "FAKEpw1", "token: FAKEpw1", 7)


def test_password_in_prose_is_a_candidate():
    m = only("hey, the staging password is tulip-Orbit4471! ok?")
    assert (m.rule, m.tier, m.value) == ("assignment", "ambiguous", "tulip-Orbit4471!")


@pytest.mark.parametrize(
    "text",
    [
        "the password is required",
        "your token is invalid",
        "password is wrong, try again",
    ],
)
def test_prose_with_a_plain_word_is_not_a_candidate(text):
    assert extract(lines(text)) == []
