import json
import shutil
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from squint.core.geometry import span_to_bbox
from squint.core.types import BBox
from squint.platforms.macos.ocr import MacOcrEngine, helper_binary, parse_helper_output


def test_parse_helper_output():
    raw = json.dumps(
        {
            "width": 100,
            "height": 50,
            "lines": [
                {
                    "text": "PASSWORD= FAKEpw1",
                    "words": [
                        {"start": 0, "end": 9, "x": 1, "y": 2, "w": 30, "h": 8},
                        {"start": 10, "end": 17, "x": 35, "y": 2, "w": 25, "h": 8},
                    ],
                }
            ],
        }
    )
    [line] = parse_helper_output(raw)
    assert line.text == "PASSWORD= FAKEpw1"
    assert line.words[1].char_start == 10
    assert line.words[1].char_end == 17
    assert line.words[1].bbox == BBox(35, 2, 25, 8)


def test_parse_helper_output_with_no_text():
    assert parse_helper_output('{"width": 1, "height": 1, "lines": []}') == []


requires_vision = pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("swiftc") is None,
    reason="needs macOS Vision and swiftc",
)


@requires_vision
def test_recognize_finds_synthetic_secret_and_its_box(tmp_path: Path):
    image = Image.new("RGB", (900, 120), "white")
    font = ImageFont.load_default(size=36)
    draw = ImageDraw.Draw(image)
    draw.text((20, 40), "TOKEN= FAKEsecret4242", fill="black", font=font)
    secret_box = draw.textbbox((20, 40), "TOKEN= FAKEsecret4242", font=font)
    path = tmp_path / "shot.png"
    image.save(path)

    engine = MacOcrEngine(helper_binary(tmp_path / "cache"))
    lines = engine.recognize(path)

    line = next(line for line in lines if "FAKEsecret4242" in line.text)
    start = line.text.index("FAKEsecret4242")
    box = span_to_bbox(line, start, start + len("FAKEsecret4242"), padding=0)
    assert box is not None
    # The secret is the right-hand part of the drawn text and sits on the same row.
    assert secret_box[0] + 50 < box.x < secret_box[2]
    assert box.x + box.width <= secret_box[2] + 15
    assert secret_box[1] - 15 < box.y < secret_box[3]
