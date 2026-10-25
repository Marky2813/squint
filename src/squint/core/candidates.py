"""Regex candidate extraction over OCR lines, sorted into tiers.

sensitive  -> flagged without asking Gemma
ambiguous  -> judged by Gemma
benign     -> dropped (never returned)
"""

import base64
import binascii
import json
import math
import re
from collections import Counter
from dataclasses import dataclass

from squint.core.types import OcrLine

SENSITIVE = "sensitive"
AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class Match:
    rule: str
    tier: str
    line: int
    start: int
    end: int
    value: str
    context: str


# (rule, tier, pattern, value group)
_RULES: list[tuple[str, str, re.Pattern, int]] = [
    (
        "private_key",
        SENSITIVE,
        re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----"),
        0,
    ),
    ("aws_key", SENSITIVE, re.compile(r"\bAKIA[0-9A-Z]{16}\b"), 0),
    (
        "github_token",
        SENSITIVE,
        re.compile(r"\b(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{30,}"),
        0,
    ),
    ("github_token", SENSITIVE, re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), 0),
    ("stripe_key", SENSITIVE, re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{10,}"), 0),
    ("slack_token", SENSITIVE, re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), 0),
    ("google_api_key", SENSITIVE, re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"), 0),
    (
        "jwt",
        SENSITIVE,
        re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
        0,
    ),
    (
        "url_credentials",
        SENSITIVE,
        re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@]+:([^\s@/]+)@"),
        1,
    ),
    ("bearer", SENSITIVE, re.compile(r"(?i)\bbearer\s+([A-Za-z0-9._~+/=-]{12,})"), 1),
    ("card", SENSITIVE, re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)"), 0),
    (
        "assignment",
        AMBIGUOUS,
        re.compile(
            r"(?i)(?<![a-z])(?:password|passwd|pwd|pass|secret|token|api[_-]?key|access[_-]?key)\w*"
            r"[\"']?(?:\s*[:=]\s*|\s+is\s+)[\"']?([^\s\"',;]+)"
        ),
        1,
    ),
    (
        "email",
        AMBIGUOUS,
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        0,
    ),
    ("phone", AMBIGUOUS, re.compile(r"(?<![\w.])\+?\d[\d ().-]{7,}\d(?![\w.])"), 0),
    ("high_entropy", AMBIGUOUS, re.compile(r"[A-Za-z0-9+/_=-]{20,}"), 0),
]

_PLACEHOLDER = re.compile(
    r"(?i)^(?:x{3,}|\*{3,}|\.{3,}|<[^>]*>|\{\{.*\}\}|\$\{.*\}|changeme|change_me|password|"
    r"secret|token|null|none|true|false|example\w*|placeholder\w*|dummy\w*|redacted|"
    r"your[_-].*|my[_-].*|test|todo|tbd)$"
)
_GENERIC_EMAIL_LOCAL = re.compile(
    r"(?i)^(?:no-?reply|do-?not-?reply|support|info|help|hello|contact|admin|sales|team|notifications?)$"
)
_RESERVED_EMAIL_DOMAIN = re.compile(
    r"(?i)(?:^|\.)(?:example\.(?:com|org|net)|localhost)$"
)
_UUID = re.compile(
    r"(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_HEX = re.compile(r"(?i)^[0-9a-f]+$")
_DATE = re.compile(r"^\d{4}[-./]\d{1,2}[-./]\d{1,2}$|^\d{1,2}[-./]\d{1,2}[-./]\d{2,4}$")
_COMMIT_CONTEXT = re.compile(r"(?i)\b(?:commit|merge|revert|sha|tree|parent)\b")
_UUID_IN_TEXT = re.compile(
    r"(?i)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)

MIN_ENTROPY = 3.5


def luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def shannon_entropy(text: str) -> float:
    counts = Counter(text)
    return -sum(n / len(text) * math.log2(n / len(text)) for n in counts.values())


def jwt_header_valid(token: str) -> bool:
    header = token.split(".", 1)[0]
    try:
        decoded = base64.urlsafe_b64decode(header + "=" * (-len(header) % 4))
        return isinstance(json.loads(decoded), dict)
    except (binascii.Error, ValueError):
        return False


def is_benign(rule: str, value: str, text: str, start: int) -> bool:
    """True for matches we drop outright: placeholders, hashes, generic addresses, dates."""
    if _PLACEHOLDER.match(value):
        return True
    if any(m.start() <= start < m.end() for m in _UUID_IN_TEXT.finditer(text)):
        return True
    if rule == "assignment" and re.search(r"\s+is\s+[\"']?$", text[:start]):
        # Prose ("the password is required"): only password-like words count.
        return not re.search(r"[\d\W_]", value)
    if rule == "card":
        return not luhn_valid(re.sub(r"\D", "", value))
    if rule == "jwt":
        return not jwt_header_valid(value)
    if rule == "email":
        local, _, domain = value.partition("@")
        return bool(
            _GENERIC_EMAIL_LOCAL.match(local) or _RESERVED_EMAIL_DOMAIN.search(domain)
        )
    if rule == "phone":
        digits = re.sub(r"\D", "", value)
        return _DATE.match(value.strip()) is not None or not 9 <= len(digits) <= 15
    if rule == "high_entropy":
        if _HEX.match(value) and len(value) in (40, 64):
            prefix = text[max(0, start - 30) : start]
            if _COMMIT_CONTEXT.search(prefix) or prefix.rstrip().endswith(
                ("sha256:", "sha1:")
            ):
                return True
        token = _whitespace_token(text, start)
        if "://" in token or token.startswith(("/", "~/", "./")):
            return True
        # Random keys of 20+ chars almost always mix letters and digits; identifiers rarely do.
        has_letter = any(c.isalpha() for c in value)
        has_digit = any(c.isdigit() for c in value)
        return not (has_letter and has_digit) or shannon_entropy(value) < MIN_ENTROPY
    return False


def _whitespace_token(text: str, pos: int) -> str:
    left = max(text.rfind(" ", 0, pos), text.rfind("\t", 0, pos)) + 1
    right = len(text)
    for sep in (" ", "\t"):
        found = text.find(sep, pos)
        if found != -1:
            right = min(right, found)
    return text[left:right]


def _context(lines: list[OcrLine], index: int, limit: int = 200) -> str:
    window = [
        lines[i].text for i in range(max(0, index - 1), min(len(lines), index + 2))
    ]
    return "\n".join(window)[:limit]


def _overlaps(a: Match, b: Match) -> bool:
    return a.line == b.line and a.start < b.end and b.start < a.end


def extract(lines: list[OcrLine]) -> list[Match]:
    """All non-benign matches. Where matches overlap, sensitive beats ambiguous and earlier rules win."""
    found: list[Match] = []
    for index, line in enumerate(lines):
        for rule, tier, pattern, group in _RULES:
            for m in pattern.finditer(line.text):
                start, end = m.span(group)
                value = m.group(group)
                if is_benign(rule, value, line.text, start):
                    continue
                candidate = Match(
                    rule, tier, index, start, end, value, _context(lines, index)
                )
                if any(_overlaps(candidate, kept) for kept in found):
                    continue
                found.append(candidate)
    return found
