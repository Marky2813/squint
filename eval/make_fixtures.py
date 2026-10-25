"""Render synthetic screenshots with planted fake secrets, and write eval/labels.json once.

    uv run python eval/make_fixtures.py

Every secret here is generated and deliberately invalid (random bodies, "FAKE" markers,
bad checksums). Each labelled value records its exact pixel box, so the eval can check
that a redaction box covers the whole secret, and that keys next to it stay readable.

labels.json is ground truth: this script refuses to overwrite it (see CLAUDE.md).
"""

import base64
import json
import random
import string
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
LABELS = HERE / "labels.json"
SEED = 20261025
HELD_OUT = 5
FONTS = Path("/System/Library/Fonts")


@dataclass(frozen=True)
class Theme:
    name: str
    font: str
    background: tuple[int, int, int]
    text: tuple[int, int, int]
    key: tuple[int, int, int]


THEMES = [
    Theme("dark-menlo", "Menlo.ttc", (30, 30, 30), (212, 212, 212), (86, 156, 214)),
    Theme("light-sfmono", "SFNSMono.ttf", (255, 255, 255), (36, 41, 47), (207, 34, 46)),
    Theme("light-helvetica", "Helvetica.ttc", (248, 248, 246), (29, 28, 29), (18, 100, 163)),
]  # fmt: skip

# A line is a list of segments: plain text, or (text, kind, category) where kind is
# "s" (sensitive: must be hidden), "n" (hard negative: must stay visible)
# or "k" (a key/label next to a secret: should stay readable).
Segment = str | tuple[str, str, str]


class Fake:
    """Generators for fake, invalid secrets and realistic hard negatives."""

    def __init__(self, rng: random.Random):
        self.rng = rng

    def chars(
        self, n: int, alphabet: str = string.ascii_letters + string.digits
    ) -> str:
        return "".join(self.rng.choice(alphabet) for _ in range(n))

    def password(self) -> str:
        words = [
            "tulip",
            "Orbit",
            "maple",
            "Quartz",
            "harbor",
            "Velvet",
            "cinder",
            "Rocket",
        ]
        return f"{self.rng.choice(words)}-{self.rng.choice(words)}{self.rng.randint(10, 9999)}!"

    def stripe(self) -> str:
        return "sk_live_FAKE" + self.chars(20)

    def aws(self) -> str:
        return "AKIAFAKE" + self.chars(12, string.ascii_uppercase + string.digits)

    def aws_secret(self) -> str:
        return self.chars(40, string.ascii_letters + string.digits + "/+")

    def github(self) -> str:
        return "ghp_" + self.chars(36)

    def slack(self) -> str:
        return f"xoxb-{self.rng.randint(10**10, 10**11)}-FAKE{self.chars(16)}"

    def jwt(self) -> str:
        def part(data: dict) -> str:
            return (
                base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")
            )

        header = part({"alg": "HS256", "typ": "JWT"})
        body = part({"sub": str(self.rng.randint(1000, 99999)), "name": "Fake User"})
        return f"{header}.{body}.{self.chars(43, string.ascii_letters + string.digits + '-_')}"

    def hex(self, n: int) -> str:
        return self.chars(n, "0123456789abcdef")

    def uuid(self) -> str:
        h = self.hex(32)
        return f"{h[:8]}-{h[8:12]}-4{h[13:16]}-a{h[17:20]}-{h[20:]}"

    def person(self) -> tuple[str, str]:
        first = self.rng.choice(
            ["Priya", "Marco", "Aiko", "Tomas", "Leila", "Owen", "Sana"]
        )
        last = self.rng.choice(
            ["Fakeworth", "Testova", "Mockridge", "Samplesen", "Dummond"]
        )
        domain = self.rng.choice(
            ["gmail.com", "fastmail.com", "proton.me", "outlook.com"]
        )
        return f"{first} {last}", f"{first.lower()}.{last.lower()}@{domain}"

    def phone(self) -> str:
        return f"+1 415 {self.rng.randint(200, 999)} {self.rng.randint(1000, 9999)}"

    def card(self) -> str:
        digits = [4] + [self.rng.randint(0, 9) for _ in range(14)]
        total = 0
        for i, d in enumerate(reversed(digits)):  # Luhn check digit
            d = d * 2 if i % 2 == 0 else d
            total += d - 9 if d > 9 else d
        digits.append((10 - total % 10) % 10)
        s = "".join(map(str, digits))
        return " ".join(s[i : i + 4] for i in range(0, 16, 4))


def S(text: str, category: str) -> tuple[str, str, str]:
    return (text, "s", category)


def N(text: str, category: str) -> tuple[str, str, str]:
    return (text, "n", category)


def K(text: str) -> tuple[str, str, str]:
    return (text, "k", "key")


def scenes(f: Fake) -> dict[str, list[list[Segment]]]:
    name, email = f.person()
    other_name, other_email = f.person()
    sha = f.hex(40)
    return {
        "env": [
            ["# .env.production"],
            [
                K("DATABASE_URL"),
                "=postgres://app:",
                S(f.password(), "password"),
                "@db.internal:5432/app",
            ],
            [K("STRIPE_SECRET_KEY"), "=", S(f.stripe(), "stripe_key")],
            [K("JWT_ACCESS_SECRET"), '="', S(f.password(), "password"), '"'],
            [K("SESSION_TOKEN"), "=", S(f.hex(48), "token")],
            ["PORT=3000"],
            [K("API_KEY"), '="', N("<YOUR_API_KEY>", "placeholder"), '"'],
            ["NODE_ENV=production"],
        ],
        "config": [
            ["# config.yaml"],
            ["service:"],
            ["  name: billing-worker"],
            ["  version: ", N("2.14.3", "version")],
            ["aws:"],
            ["  ", K("access_key_id"), ": ", S(f.aws(), "aws_key")],
            ["  ", K("secret_access_key"), ": ", S(f.aws_secret(), "aws_secret")],
            ["github:"],
            ["  ", K("token"), ": ", S(f.github(), "github_token")],
            ["  webhook_id: ", N(f.uuid(), "uuid")],
        ],
        "terminal": [
            ["$ export ", K("SLACK_BOT_TOKEN"), "=", S(f.slack(), "slack_token")],
            ["$ curl -H 'Authorization: Bearer ", S(f.jwt(), "jwt"), "' \\"],
            ["    https://api.internal/v1/me"],
            ['{"id": "', N(f.uuid(), "uuid"), '", "status": "ok"}'],
            ["$ git rev-parse HEAD"],
            [N(sha, "commit_sha")],
        ],
        "chat": [
            [name, "  10:42 AM"],
            ["hey can you log into staging? password is ", S(f.password(), "password")],
            [other_name, "  10:44 AM"],
            [
                "sure, also ping me at ",
                S(other_email, "email"),
                " or ",
                S(f.phone(), "phone"),
            ],
            [name, "  10:45 AM"],
            ["thanks! release notes are in the wiki, build ", N("2026-10-25", "date")],
        ],
        "gitlog": [
            ["commit ", N(sha, "commit_sha")],
            ["Author: ", name, " <", S(email, "email"), ">"],
            ["Date:   Sat Oct 25 10:42:00 2026 +0530"],
            [""],
            ["    fix: retry webhook delivery"],
            [""],
            [
                "    Co-authored-by: bot <",
                N("noreply@github.com", "generic_email"),
                ">",
            ],
        ],
        "readme": [
            ["## Setup"],
            ["1. Copy .env.example to .env"],
            ["2. Set ", K("STRIPE_KEY"), "=", N("sk_test_xxxxxxxxxxxx", "placeholder")],
            ["3. Email ", N("support@example.com", "generic_email"), " for access"],
            ["4. Request id format: ", N(f.uuid(), "uuid")],
        ],
        "dashboard": [
            ["Customers                                  Export"],
            ["Name                Email                         Card"],
            [name, "      ", S(email, "email"), "      ", S(f.card(), "card")],
            [
                other_name,
                "      ",
                S(other_email, "email"),
                "      ",
                S(f.card(), "card"),
            ],
            ["Test card for QA: ", N("4242 4242 4242 4242", "test_card")],
        ],
        "clean": [
            ["def fibonacci(n: int) -> int:"],
            ["    a, b = 0, 1"],
            ["    for _ in range(n):"],
            ["        a, b = b, a + b"],
            ["    return a"],
        ],
    }


def render(lines: list[list[Segment]], theme: Theme) -> tuple[Image.Image, list[dict]]:
    font = ImageFont.truetype(str(FONTS / theme.font), 26)
    margin, line_height = 40, 46
    width = 1700
    image = Image.new(
        "RGB", (width, margin * 2 + line_height * len(lines)), theme.background
    )
    draw = ImageDraw.Draw(image)
    items = []
    for row, segments in enumerate(lines):
        y = margin + row * line_height
        x = margin
        for segment in segments:
            text, kind, category = (
                segment if isinstance(segment, tuple) else (segment, "", "")
            )
            colour = theme.key if kind == "k" else theme.text
            draw.text((x, y), text, font=font, fill=colour)
            if kind:
                left, top, right, bottom = draw.textbbox((x, y), text, font=font)
                items.append(
                    {
                        "value": text,
                        "category": category,
                        "sensitive": kind == "s",
                        "keep_visible": kind == "k",
                        "bbox": [left, top, right - left, bottom - top],
                    }
                )
            x += font.getlength(text)
    return image, items


def main() -> int:
    if LABELS.exists():
        print(
            f"{LABELS} already exists and is read-only ground truth; not regenerating."
        )
        return 1
    rng = random.Random(SEED)
    FIXTURES.mkdir(exist_ok=True)
    screenshots = {}
    for theme in THEMES:
        for scene, lines in scenes(Fake(rng)).items():
            name = f"{scene}-{theme.name}.png"
            image, items = render(lines, theme)
            image.save(FIXTURES / name)
            screenshots[name] = {"held_out": False, "items": items}
    for name in rng.sample(sorted(screenshots), HELD_OUT):
        screenshots[name]["held_out"] = True
    LABELS.write_text(
        json.dumps({"version": 1, "screenshots": screenshots}, indent=2) + "\n"
    )
    sensitive = sum(i["sensitive"] for s in screenshots.values() for i in s["items"])
    print(
        f"wrote {len(screenshots)} screenshots, {sensitive} sensitive items, to {FIXTURES}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
