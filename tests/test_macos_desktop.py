import shutil
import subprocess
import sys

import pytest
from PIL import Image

from squint.platforms.macos.desktop import MacDesktop, applescript_string

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
