"""Watch the macOS clipboard for new images and write redacted images back."""

import queue
import subprocess
import threading
from pathlib import Path

from squint.platforms.macos.build import CACHE_DIR, compile_swift

SOURCE = Path(__file__).with_name("clipboard.swift")
REPLY_TIMEOUT_SECONDS = 5.0
READY_TIMEOUT_SECONDS = 10.0


def clipboard_binary(cache_dir: Path = CACHE_DIR) -> Path:
    return compile_swift([SOURCE], cache_dir / "squint-clip")


class ClipboardWatcher:
    """Runs the helper; new clipboard images arrive as PNG paths inside `folder`."""

    def __init__(self, folder: Path, binary: Path | None = None):
        self.images: queue.Queue[Path] = queue.Queue()
        self.replies: queue.Queue[str] = queue.Queue()
        self.ready = threading.Event()
        self.lock = threading.Lock()
        self.process = subprocess.Popen(
            [str(binary or clipboard_binary()), str(folder)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=self._read, daemon=True).start()
        if not self.ready.wait(READY_TIMEOUT_SECONDS):
            self.close()
            raise OSError("clipboard helper did not start")

    def _read(self) -> None:
        for line in self.process.stdout:
            line = line.rstrip("\n")
            if line == "ready":
                self.ready.set()
            elif line.startswith("image "):
                self.images.put(Path(line[len("image ") :]))
            elif line in ("copied", "error"):
                self.replies.put(line)

    def poll(self) -> list[Path]:
        found = []
        while not self.images.empty():
            found.append(self.images.get_nowait())
        return found

    def copy(self, path: Path) -> None:
        """Put the PNG on the clipboard, tagged so this watcher ignores it. Raises OSError."""
        if "\n" in str(path):
            raise OSError("path contains a newline")
        with self.lock:
            try:
                self.process.stdin.write(f"copy {path}\n")
                self.process.stdin.flush()
                reply = self.replies.get(timeout=REPLY_TIMEOUT_SECONDS)
            except (BrokenPipeError, queue.Empty) as error:
                raise OSError("clipboard helper not responding") from error
        if reply != "copied":
            raise OSError(f"clipboard copy failed for {path.name}")

    def close(self) -> None:
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
