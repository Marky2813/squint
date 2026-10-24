"""Interfaces each platform must implement."""

from pathlib import Path
from typing import Protocol

from squint.core.types import OcrLine


class OcrEngine(Protocol):
    def recognize(self, image_path: Path) -> list[OcrLine]:
        """Return recognised lines with per-word boxes in image pixel coordinates."""
        ...
