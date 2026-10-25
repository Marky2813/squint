"""macOS desktop integration via stock command-line tools (no extra dependencies)."""

import subprocess
from pathlib import Path


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
