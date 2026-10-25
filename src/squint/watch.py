"""squint watch: scan each new screenshot as it lands in the screenshot folder."""

import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from squint.core.classify import OllamaClassifier
from squint.core.pipeline import Classifier, analyze
from squint.core.review import ReviewSession
from squint.platforms.base import Desktop, OcrEngine
from squint.server import ReviewServer

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def is_screenshot(path: Path) -> bool:
    return (
        path.suffix.lower() in IMAGE_SUFFIXES
        and not path.name.startswith(".")
        and not path.name.endswith(".redacted.png")
    )


class FolderWatcher:
    """Reports files that appear after start-up once their size has stopped changing."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.seen = {p for p in folder.iterdir() if is_screenshot(p)}
        self.sizes: dict[Path, int] = {}

    def poll(self) -> list[Path]:
        ready = []
        for path in sorted(self.folder.iterdir()):
            if path in self.seen or not is_screenshot(path):
                continue
            try:
                size = path.stat().st_size
            except FileNotFoundError:
                continue
            if size > 0 and self.sizes.get(path) == size:
                self.seen.add(path)
                self.sizes.pop(path)
                ready.append(path)
            else:
                self.sizes[path] = size
        return ready


def warm_up_ocr(ocr: OcrEngine) -> None:
    """Run OCR once on a throwaway image so Vision's first-use cost is paid at start-up."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "warmup.png"
        image = Image.new("RGB", (400, 80), "white")
        ImageDraw.Draw(image).text(
            (10, 20),
            "squint warm up",
            fill="black",
            font=ImageFont.load_default(size=28),
        )
        image.save(path)
        ocr.recognize(path)


def handle(
    path: Path,
    ocr: OcrEngine,
    classifier: Classifier,
    server: ReviewServer,
    desktop: Desktop,
    quiet: bool,
) -> None:
    started = time.perf_counter()
    try:
        lines = ocr.recognize(path)
    except (OSError, subprocess.SubprocessError, ValueError):
        desktop.notify("Squint", f"Couldn't scan {path.name}")
        print(f"{path.name}: OCR failed")
        return
    result = analyze(lines, classifier)
    elapsed = time.perf_counter() - started
    print(f"{path.name}: {len(result.flagged)} flagged in {elapsed:.2f}s")
    if not result.findings:
        if not quiet:
            desktop.notify("Squint", f"✓ {path.name} looks clean")
        return
    server.show(ReviewSession(path, result))
    if not server.page_open():
        desktop.open_url(server.url)


def run(
    ocr: OcrEngine, desktop: Desktop, quiet: bool = False, interval: float = 0.1
) -> None:
    folder = desktop.screenshot_dir()
    classifier = OllamaClassifier()
    print("warming up OCR and Gemma…")
    warm_up_ocr(ocr)
    if not classifier.warm_up():
        print("warning: Gemma unavailable; every ambiguous match will be flagged")
    server = ReviewServer(on_export=desktop.copy_image)
    server.start()
    watcher = FolderWatcher(folder)
    print(f"watching {folder} (Ctrl-C to stop)")
    try:
        while True:
            for path in watcher.poll():
                handle(path, ocr, classifier, server, desktop, quiet)
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
