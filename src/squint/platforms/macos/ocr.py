"""macOS OCR via a small Swift helper that wraps Apple Vision."""

import json
import subprocess
from pathlib import Path

from squint.core.types import BBox, OcrLine, OcrWord
from squint.platforms.macos.build import CACHE_DIR, compile_swift

SOURCE = Path(__file__).with_name("ocr.swift")
# Vision prepares its recognition models on first use on a machine (~60 s, once);
# later runs take ~0.2-0.4 s.
TIMEOUT_SECONDS = 120


def parse_helper_output(raw: str) -> list[OcrLine]:
    data = json.loads(raw)
    return [
        OcrLine(
            text=line["text"],
            words=tuple(
                OcrWord(
                    char_start=int(w["start"]),
                    char_end=int(w["end"]),
                    bbox=BBox(w["x"], w["y"], w["w"], w["h"]),
                )
                for w in line["words"]
            ),
        )
        for line in data["lines"]
    ]


def helper_binary(cache_dir: Path = CACHE_DIR) -> Path:
    return compile_swift([SOURCE], cache_dir / "squint-ocr")


class MacOcrEngine:
    def __init__(self, binary: Path | None = None):
        self.binary = binary or helper_binary()

    def recognize(self, image_path: Path) -> list[OcrLine]:
        result = subprocess.run(
            [str(self.binary), str(image_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        return parse_helper_output(result.stdout)
