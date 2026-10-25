import shutil
import subprocess
import sys

import pytest
from PIL import Image

from squint.platforms.macos.desktop import (
    MacDesktop,
    applescript_string,
    disable_screenshot_thumbnail,
    read_thumbnail_setting,
)

on_mac = pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("osascript") is None,
    reason="needs macOS",
)


def test_applescript_string_escapes_quotes_and_backslashes():
    assert applescript_string('a "b" \\c') == '"a \\"b\\" \\\\c"'


@on_mac
def test_screenshot_dir_exists():
    assert MacDesktop().screenshot_dir().is_dir()


@on_mac
def test_copy_image_puts_png_on_clipboard(tmp_path):
    path = tmp_path / 'odd "name".png'
    Image.new("RGB", (4, 4), "red").save(path)
    MacDesktop().copy_image(path)
    info = subprocess.run(
        ["osascript", "-e", "clipboard info"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "PNGf" in info


@on_mac
def test_copy_image_missing_file_raises_oserror(tmp_path):
    with pytest.raises(OSError):
        MacDesktop().copy_image(tmp_path / "missing.png")


class FakeDefaults:
    """In-memory stand-in for the `defaults` command."""

    def __init__(self, value=None):
        self.value = value
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        verb = args[1]
        if verb == "read":
            if self.value is None:
                return subprocess.CompletedProcess(args, 1, "", "not found")
            return subprocess.CompletedProcess(args, 0, f"{self.value}\n", "")
        if verb == "write":
            self.value = 1 if args[-1] == "true" else 0
        elif verb == "delete":
            self.value = None
        return subprocess.CompletedProcess(args, 0, "", "")


def test_read_thumbnail_setting():
    assert read_thumbnail_setting(FakeDefaults(None)) is None
    assert read_thumbnail_setting(FakeDefaults(1)) is True
    assert read_thumbnail_setting(FakeDefaults(0)) is False


@pytest.mark.parametrize("initial", [None, 0, 1])
def test_disable_then_restore_returns_to_initial_state(initial, tmp_path):
    defaults = FakeDefaults(initial)
    state = tmp_path / "state.json"
    restore = disable_screenshot_thumbnail(defaults, state)
    assert defaults.value == 0
    assert state.exists()
    restore()
    assert defaults.value == initial
    assert not state.exists()


def test_restore_deletes_key_when_it_was_unset(tmp_path):
    defaults = FakeDefaults(None)
    disable_screenshot_thumbnail(defaults, tmp_path / "state.json")()
    assert defaults.calls[-1][:2] == ["defaults", "delete"]


def test_crashed_run_still_restores_true_original(tmp_path):
    defaults = FakeDefaults(None)
    state = tmp_path / "state.json"
    disable_screenshot_thumbnail(defaults, state)  # run dies without restoring
    assert defaults.value == 0
    restore = disable_screenshot_thumbnail(defaults, state)  # next run
    restore()
    assert defaults.value is None
