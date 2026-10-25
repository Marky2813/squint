"""Build dist/Squint.app and dist/Squint.dmg: a double-click install, no terminal needed.

    uv run python scripts/build_app.py

The app bundles a standalone CPython (the uv-managed python-build-standalone build),
Squint and its dependencies, and prebuilt Swift helpers. It is ad-hoc signed; a public
release needs a Developer ID signature and notarization instead.
"""

import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MACOS = ROOT / "src" / "squint" / "platforms" / "macos"
DIST = ROOT / "dist"
APP = DIST / "Squint.app"
PYTHON_VERSION = "3.15"
# Parts of the standard library Squint never uses; dropping them keeps the app small.
STDLIB_SKIP = {
    "test", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3", "pydoc_data",
    "__pycache__",
}  # fmt: skip


def run(*args: str | Path, **kwargs) -> subprocess.CompletedProcess:
    print("+", " ".join(map(str, args)))
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def standalone_python() -> Path:
    """Root of a relocatable uv-managed CPython (never Homebrew or the system Python)."""
    run("uv", "python", "install", PYTHON_VERSION)
    found = run(
        "uv", "python", "find", "--managed-python", "--no-project", PYTHON_VERSION,
        capture_output=True, text=True,
    ).stdout.strip()  # fmt: skip
    return Path(found).resolve().parent.parent


def copy_python(contents: Path) -> Path:
    target = contents / "Resources" / "python"
    source = standalone_python()

    def ignore(directory: str, names: list[str]) -> set[str]:
        skip = {
            n for n in names if n in STDLIB_SKIP or n.startswith(("tcl", "tk", "itcl"))
        }
        if Path(directory) == source:
            skip |= {"include", "share"}
        return skip

    shutil.copytree(source, target, symlinks=True, ignore=ignore)
    for marker in target.glob("lib/python*/EXTERNALLY-MANAGED"):
        marker.unlink()  # this copy belongs to Squint
    python = target / "bin" / "python3"
    run("uv", "pip", "install", "--python", python, "--no-cache", ROOT)
    run(
        python, "-m", "compileall", "-q", "-j0", target / "lib"
    )  # no .pyc writes at runtime
    return python


def build_swift(contents: Path) -> None:
    executable = contents / "MacOS" / "Squint"
    executable.parent.mkdir(parents=True)
    run(
        "swiftc",
        "-O",
        "-parse-as-library",
        MACOS / "app" / "SquintApp.swift",
        "-o",
        executable,
    )
    bin_dir = contents / "Resources" / "bin"
    bin_dir.mkdir(parents=True)
    run("swiftc", "-O", MACOS / "ocr.swift", "-o", bin_dir / "squint-ocr")
    run("swiftc", "-O", MACOS / "clipboard.swift", "-o", bin_dir / "squint-clip")


def build_icon(contents: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        master = Path(tmp) / "icon.png"
        run(contents / "MacOS" / "Squint", "--render-icon", master)
        iconset = Path(tmp) / "Squint.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
                run("sips", "-z", size * scale, size * scale, master, "--out", iconset / name,
                    capture_output=True)  # fmt: skip
        run(
            "iconutil",
            "-c",
            "icns",
            iconset,
            "-o",
            contents / "Resources" / "Squint.icns",
        )


def write_info_plist(contents: Path) -> None:
    with open(MACOS / "app" / "Info.plist", "rb") as f:
        info = plistlib.load(f)
    info["CFBundleIconFile"] = "Squint"
    with open(contents / "Info.plist", "wb") as f:
        plistlib.dump(info, f)


def build_dmg() -> Path:
    dmg = DIST / "Squint.dmg"
    dmg.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "Squint"
        stage.mkdir()
        shutil.copytree(APP, stage / "Squint.app", symlinks=True)
        (stage / "Applications").symlink_to("/Applications")
        run("hdiutil", "create", "-volname", "Squint", "-srcfolder", stage,
            "-ov", "-format", "UDZO", dmg, capture_output=True)  # fmt: skip
    return dmg


def main() -> int:
    if APP.exists():
        shutil.rmtree(APP)
    contents = APP / "Contents"
    build_swift(contents)
    build_icon(contents)
    write_info_plist(contents)
    python = copy_python(contents)
    run(
        python, "-c", "import squint.cli, PIL, requests"
    )  # the bundle is self-contained
    run("codesign", "--force", "--deep", "--sign", "-", APP)
    dmg = build_dmg()
    size = run("du", "-sh", APP, capture_output=True, text=True).stdout.split()[0]
    print(f"\nbuilt {APP} ({size}) and {dmg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
