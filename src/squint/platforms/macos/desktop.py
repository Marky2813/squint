"""macOS desktop integration via stock command-line tools (no extra dependencies)."""

import json
import subprocess
from pathlib import Path

from squint.platforms.macos.build import CACHE_DIR


def applescript_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


class MacDesktop:
    def screenshot_dir(self) -> Path:
        result = subprocess.run(
            ["defaults", "read", "com.apple.screencapture", "location"],
            capture_output=True,
            text=True,
            check=False,
        )
        configured = Path(result.stdout.strip()).expanduser()
        if result.returncode == 0 and configured.is_dir():
            return configured
        return Path.home() / "Desktop"

    def copy_image(self, path: Path) -> None:
        script = (
            f"set the clipboard to (read (POSIX file {applescript_string(str(path))})"
            " as «class PNGf»)"
        )
        try:
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
        except subprocess.CalledProcessError as error:
            raise OSError(f"clipboard copy failed: {error.stderr!r}") from error

    def notify(self, title: str, message: str) -> None:
        script = (
            f"display notification {applescript_string(message)}"
            f" with title {applescript_string(title)}"
        )
        subprocess.run(["osascript", "-e", script], capture_output=True, check=False)

    def open_url(self, url: str) -> None:
        subprocess.run(["open", url], check=False)

    def disable_screenshot_thumbnail(self):
        return disable_screenshot_thumbnail()


THUMBNAIL_DOMAIN = "com.apple.screencapture"
THUMBNAIL_KEY = "show-thumbnail"


def read_thumbnail_setting(run=subprocess.run) -> bool | None:
    """Current show-thumbnail value, or None if the key is unset (macOS default: on)."""
    result = run(
        ["defaults", "read", THUMBNAIL_DOMAIN, THUMBNAIL_KEY],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() == "1"


def write_thumbnail_setting(value: bool | None, run=subprocess.run) -> None:
    """Set show-thumbnail; None deletes the key so macOS falls back to its default."""
    if value is None:
        args = ["defaults", "delete", THUMBNAIL_DOMAIN, THUMBNAIL_KEY]
    else:
        flag = "true" if value else "false"
        args = ["defaults", "write", THUMBNAIL_DOMAIN, THUMBNAIL_KEY, "-bool", flag]
    run(args, capture_output=True, check=False)


THUMBNAIL_STATE = CACHE_DIR / "thumbnail-original.json"


def disable_screenshot_thumbnail(
    run=subprocess.run, state_file: Path = THUMBNAIL_STATE
):
    """Turn off the floating thumbnail (it delays saving); returns a function that restores it.

    The original value is saved to state_file first. If an earlier run died before restoring,
    that saved value (not the current "off") is what gets restored.
    """
    if state_file.exists():
        previous = json.loads(state_file.read_text())["show_thumbnail"]
    else:
        previous = read_thumbnail_setting(run)
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps({"show_thumbnail": previous}))
    write_thumbnail_setting(False, run)

    def restore() -> None:
        write_thumbnail_setting(previous, run)
        state_file.unlink(missing_ok=True)

    return restore
