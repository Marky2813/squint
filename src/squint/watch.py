"""squint watch: scan each new screenshot as it lands in the screenshot folder."""

import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from squint.core.classify import OllamaClassifier
from squint.core.pipeline import Classifier, analyze
from squint.core.review import ReviewSession
from squint.platforms.base import Clipboard, Desktop, OcrEngine
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
    source: str,
    ocr: OcrEngine,
    classifier: Classifier,
    server: ReviewServer,
    desktop: Desktop,
    quiet: bool,
) -> None:
    """Scan one image. Flagged results go to review (and, in live mode, the clipboard)."""
    started = time.perf_counter()
    try:
        lines = ocr.recognize(path)
    except (OSError, subprocess.SubprocessError, ValueError):
        desktop.notify("Squint", f"Couldn't scan {path.name}")
        print(f"{path.name}: OCR failed")
        return
    result = analyze(lines, classifier)
    elapsed = time.perf_counter() - started
    print(f"{source}: {len(result.flagged)} flagged in {elapsed:.2f}s")
    if not result.flagged:
        if source == "clipboard":
            path.unlink(missing_ok=True)  # never keep clean clipboard images around
        elif not quiet:
            desktop.notify("Squint", f"✓ {path.name} looks clean")
        return
    server.show(ReviewSession(path, result, source))
    if not server.page_open():
        desktop.open_url(server.url)


def stop_on_signals() -> None:
    """Treat terminal close and kill like Ctrl-C so cleanup (thumbnail restore) still runs."""
    if threading.current_thread() is not threading.main_thread():
        return

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, interrupt)


def run(
    ocr: OcrEngine,
    desktop: Desktop,
    make_clipboard: Callable[[Path], Clipboard],
    launch_ui: Callable[[str], subprocess.Popen | None],
    quiet: bool = False,
    interval: float = 0.1,
) -> None:
    folder = desktop.screenshot_dir()
    classifier = OllamaClassifier()
    print("warming up OCR and Gemma…")
    warm_up_ocr(ocr)
    if not classifier.warm_up():
        print("warning: Gemma unavailable; every ambiguous match will be flagged")

    stop_on_signals()
    restore_thumbnail = desktop.disable_screenshot_thumbnail()
    print("turned off the screenshot floating thumbnail (restored when Squint exits)")
    with tempfile.TemporaryDirectory(prefix="squint-") as tmp:  # created 0700
        clipboard = make_clipboard(Path(tmp))
        server = ReviewServer(on_export=clipboard.copy, live=True)
        server.start()
        ui = launch_ui(server.url)
        folder_watcher = FolderWatcher(folder)
        print(f"watching {folder} and the clipboard (Ctrl-C to stop)")
        try:
            while True:
                for path in folder_watcher.poll():
                    handle(path, "file", ocr, classifier, server, desktop, quiet)
                for path in clipboard.poll():
                    handle(path, "clipboard", ocr, classifier, server, desktop, quiet)
                time.sleep(interval)
        except KeyboardInterrupt:
            pass
        finally:
            restore_thumbnail()
            if ui is not None:
                ui.terminate()
            clipboard.close()
            server.stop()
