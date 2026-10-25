"""Compile bundled Swift sources on first use, and again whenever a source changes."""

import subprocess
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "squint"


def is_stale(target: Path, sources: list[Path]) -> bool:
    if not target.exists():
        return True
    built = target.stat().st_mtime
    return any(source.stat().st_mtime > built for source in sources)


def compile_swift(
    sources: list[Path], output: Path, extra_args: tuple[str, ...] = ()
) -> Path:
    if is_stale(output, sources):
        output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["swiftc", "-O", *extra_args, *map(str, sources), "-o", str(output)],
            check=True,
            capture_output=True,
        )
    return output
