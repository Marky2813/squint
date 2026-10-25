import shutil
import subprocess
import sys
import time

import pytest
from PIL import Image

from squint.platforms.macos.clipboard import ClipboardWatcher, clipboard_binary

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("swiftc") is None,
    reason="needs macOS and swiftc",
)


def put_image_with_osascript(path):
    script = f'set the clipboard to (read (POSIX file "{path}") as «class PNGf»)'
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True)


def wait_for(watcher, seconds=3.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if found := watcher.poll():
            return found
        time.sleep(0.05)
    return []


@pytest.fixture
def watcher(tmp_path):
    (tmp_path / "clips").mkdir()
    w = ClipboardWatcher(tmp_path / "clips", clipboard_binary(tmp_path / "cache"))
    time.sleep(0.3)
    yield w
    w.close()


def test_new_clipboard_image_is_reported_as_png(tmp_path, watcher):
    source = tmp_path / "copied.png"
    Image.new("RGB", (8, 6), "blue").save(source)
    put_image_with_osascript(source)
    [path] = wait_for(watcher)
    with Image.open(path) as image:
        assert image.size == (8, 6)


def test_own_copies_are_not_reported(tmp_path, watcher):
    redacted = tmp_path / "x.redacted.png"
    Image.new("RGB", (5, 5), "green").save(redacted)
    watcher.copy(redacted)
    assert wait_for(watcher, seconds=1.0) == []
    info = subprocess.run(
        ["osascript", "-e", "clipboard info"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "PNGf" in info


def test_copy_missing_file_raises(tmp_path, watcher):
    with pytest.raises(OSError):
        watcher.copy(tmp_path / "missing.png")


def test_copy_rejects_newline_paths(tmp_path, watcher):
    with pytest.raises(OSError):
        watcher.copy(tmp_path / "bad\nname.png")


def test_helper_exits_when_closed(watcher):
    watcher.close()
    assert watcher.process.poll() is not None
