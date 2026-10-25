import subprocess
from pathlib import Path

from PIL import Image

from squint.core.classify import Verdicts
from squint.core.types import BBox, OcrLine, OcrWord
from squint.server import ReviewServer
from squint.watch import FolderWatcher, handle, is_screenshot


def test_is_screenshot():
    assert is_screenshot(Path("Screenshot 2026-10-25 at 10.00.00.png"))
    assert is_screenshot(Path("shot.JPG"))
    assert not is_screenshot(Path(".Screenshot 2026-10-25.png"))
    assert not is_screenshot(Path("shot.redacted.png"))
    assert not is_screenshot(Path("notes.txt"))


def test_existing_files_are_ignored(tmp_path):
    (tmp_path / "old.png").write_bytes(b"x")
    watcher = FolderWatcher(tmp_path)
    assert watcher.poll() == []
    assert watcher.poll() == []


def test_new_file_reported_once_size_is_stable(tmp_path):
    watcher = FolderWatcher(tmp_path)
    shot = tmp_path / "new.png"
    shot.write_bytes(b"abc")
    assert watcher.poll() == []  # first sighting
    shot.write_bytes(b"abcdef")
    assert watcher.poll() == []  # still growing
    assert watcher.poll() == [shot]  # unchanged since last poll
    assert watcher.poll() == []  # never reported twice


def test_empty_file_waits(tmp_path):
    watcher = FolderWatcher(tmp_path)
    (tmp_path / "new.png").write_bytes(b"")
    assert watcher.poll() == []
    assert watcher.poll() == []


def test_hidden_and_redacted_files_are_skipped(tmp_path):
    watcher = FolderWatcher(tmp_path)
    (tmp_path / ".tmp.png").write_bytes(b"x")
    (tmp_path / "a.redacted.png").write_bytes(b"x")
    watcher.poll()
    assert watcher.poll() == []


def test_file_removed_before_stable_is_dropped(tmp_path):
    watcher = FolderWatcher(tmp_path)
    shot = tmp_path / "new.png"
    shot.write_bytes(b"abc")
    watcher.poll()
    shot.unlink()
    assert watcher.poll() == []


FAKE_AWS = "AKIA" + "FAKE" * 4


class FakeOcr:
    def __init__(self, lines=None, error=None):
        self.lines = lines or []
        self.error = error

    def recognize(self, path):
        if self.error:
            raise self.error
        return self.lines


class FakeDesktop:
    def __init__(self):
        self.notes, self.opened = [], []

    def notify(self, title, message):
        self.notes.append(message)

    def open_url(self, url):
        self.opened.append(url)


class NoGemma:
    def judge_all(self, candidates):
        return Verdicts({c.id: True for c in candidates}, False)


def shot(tmp_path):
    path = tmp_path / "Screenshot.png"
    Image.new("RGB", (300, 40), "white").save(path)
    return path


def test_handle_clean_screenshot_notifies_and_opens_nothing(tmp_path):
    desktop, server = FakeDesktop(), ReviewServer()
    handle(
        shot(tmp_path),
        FakeOcr([OcrLine("hello", ())]),
        NoGemma(),
        server,
        desktop,
        quiet=False,
    )
    assert desktop.notes == ["✓ Screenshot.png looks clean"]
    assert desktop.opened == [] and server.session is None


def test_handle_clean_screenshot_quiet_mode_is_silent(tmp_path):
    desktop = FakeDesktop()
    handle(shot(tmp_path), FakeOcr([]), NoGemma(), ReviewServer(), desktop, quiet=True)
    assert desktop.notes == []


def test_handle_ocr_failure_notifies(tmp_path):
    desktop = FakeDesktop()
    ocr = FakeOcr(error=subprocess.CalledProcessError(1, "squint-ocr"))
    handle(shot(tmp_path), ocr, NoGemma(), ReviewServer(), desktop, quiet=True)
    assert desktop.notes == ["Couldn't scan Screenshot.png"]


def test_handle_findings_shows_review_and_opens_browser(tmp_path):
    desktop, server = FakeDesktop(), ReviewServer()
    line = OcrLine(f"id {FAKE_AWS}", (OcrWord(3, 23, BBox(30, 5, 200, 20)),))
    handle(shot(tmp_path), FakeOcr([line]), NoGemma(), server, desktop, quiet=True)
    assert server.session is not None
    assert server.session.to_json()["findings"][0]["rule"] == "aws_key"
    assert desktop.opened == [server.url]


def test_handle_does_not_reopen_browser_when_page_is_open(tmp_path):
    desktop, server = FakeDesktop(), ReviewServer()
    server.last_poll = float("inf")
    line = OcrLine(f"id {FAKE_AWS}", (OcrWord(3, 23, BBox(30, 5, 200, 20)),))
    handle(shot(tmp_path), FakeOcr([line]), NoGemma(), server, desktop, quiet=True)
    assert desktop.opened == []
