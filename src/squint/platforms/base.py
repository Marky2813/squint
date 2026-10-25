"""Interfaces each platform must implement."""

from pathlib import Path
from typing import Protocol

from squint.core.types import OcrLine


class OcrEngine(Protocol):
    def recognize(self, image_path: Path) -> list[OcrLine]:
        """Return recognised lines with per-word boxes in image pixel coordinates."""
        ...


class Desktop(Protocol):
    def screenshot_dir(self) -> Path:
        """Folder where the OS saves new screenshots."""
        ...

    def copy_image(self, path: Path) -> None:
        """Put the PNG at path on the clipboard. Raises OSError on failure."""
        ...

    def notify(self, title: str, message: str) -> None:
        """Show a passive notification. Must never raise."""
        ...

    def open_url(self, url: str) -> None:
        """Open url in the user's browser."""
        ...
