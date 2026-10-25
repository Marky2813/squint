"""Build and launch the native review app (a thin client of the local review API)."""

import shutil
import subprocess
from pathlib import Path

from squint.platforms.macos.build import CACHE_DIR, compile_swift

APP_DIR = Path(__file__).with_name("app")
SOURCE = APP_DIR / "SquintApp.swift"
INFO_PLIST = APP_DIR / "Info.plist"


def app_bundle(cache_dir: Path = CACHE_DIR) -> Path:
    """Assemble Squint.app in the cache; recompiles only when the Swift source changes."""
    bundle = cache_dir / "Squint.app"
    contents = bundle / "Contents"
    compile_swift(
        [SOURCE], contents / "MacOS" / "Squint", extra_args=("-parse-as-library",)
    )
    shutil.copyfile(INFO_PLIST, contents / "Info.plist")
    return bundle


def launch(url: str, bundle: Path | None = None) -> subprocess.Popen:
    """Start the app as a child process so it exits when Squint stops."""
    executable = (bundle or app_bundle()) / "Contents" / "MacOS" / "Squint"
    return subprocess.Popen(
        [str(executable), "--url", url],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
