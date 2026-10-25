"""Build dist/Squint.app and dist/Squint.dmg: a double-click install, no terminal needed.

    uv run python scripts/build_app.py                       # ad-hoc signed, for testing
    uv run python scripts/build_app.py \\
        --sign "Developer ID Application: Name (TEAMID)" \\
        --notarize squint-notary                             # a release anyone can open

The app is universal (Apple Silicon + Intel). It bundles a standalone CPython per
architecture (uv-managed python-build-standalone builds), Squint and its dependencies,
and universal Swift binaries; the app starts the Python that matches the Mac.

--notarize takes a notarytool keychain profile, created once with:
    xcrun notarytool store-credentials squint-notary \\
        --apple-id you@example.com --team-id TEAMID --password <app-specific password>
"""

import argparse
import platform
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
ARCHS = ("arm64", "x86_64")
UV_ARCH = {"arm64": "aarch64", "x86_64": "x86_64"}  # uv's names for them
MIN_MACOS = "14.0"
# Parts of the standard library Squint never uses; dropping them keeps the app small.
STDLIB_SKIP = {
    "test", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3", "pydoc_data",
    "__pycache__",
}  # fmt: skip
MACHO_MAGIC = {
    b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
}  # fmt: skip


def run(*args: str | Path, **kwargs) -> subprocess.CompletedProcess:
    print("+", " ".join(map(str, args)))
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


# MARK: Swift


def build_swift_universal(
    source: Path, output: Path, extra: tuple[str, ...] = ()
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        slices = []
        for arch in ARCHS:
            slice_path = Path(tmp) / arch
            run("swiftc", "-O", "-target", f"{arch}-apple-macos{MIN_MACOS}", *extra,
                source, "-o", slice_path)  # fmt: skip
            slices.append(slice_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        run("lipo", "-create", *slices, "-output", output)


def build_swift(contents: Path) -> None:
    build_swift_universal(
        MACOS / "app" / "SquintApp.swift",
        contents / "MacOS" / "Squint",
        ("-parse-as-library",),
    )
    bin_dir = contents / "Resources" / "bin"
    build_swift_universal(MACOS / "ocr.swift", bin_dir / "squint-ocr")
    build_swift_universal(MACOS / "clipboard.swift", bin_dir / "squint-clip")


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
        icns = contents / "Resources" / "Squint.icns"
        run("iconutil", "-c", "icns", iconset, "-o", icns)


def write_info_plist(contents: Path) -> None:
    with open(MACOS / "app" / "Info.plist", "rb") as f:
        info = plistlib.load(f)
    info["CFBundleIconFile"] = "Squint"
    with open(contents / "Info.plist", "wb") as f:
        plistlib.dump(info, f)


# MARK: Python


def standalone_python(arch: str) -> Path:
    """Root of a relocatable uv-managed CPython for arch (never Homebrew or system Python).

    Found by directory rather than `uv python find`, which would have to run it: an Intel
    Python can't run on an Apple Silicon Mac without Rosetta.
    """
    run(
        "uv",
        "python",
        "install",
        f"cpython-{PYTHON_VERSION}-macos-{UV_ARCH[arch]}-none",
    )
    root = Path(
        run("uv", "python", "dir", capture_output=True, text=True).stdout.strip()
    )
    found = sorted(root.glob(f"cpython-{PYTHON_VERSION}.*-macos-{UV_ARCH[arch]}-none"))
    if not found:
        raise SystemExit(f"no uv-managed Python {PYTHON_VERSION} for {arch} in {root}")
    return found[-1].resolve()


def build_wheel(out: Path) -> Path:
    run("uv", "build", "--wheel", "--out-dir", out, ROOT, capture_output=True)
    return next(out.glob("squint-*.whl"))


def copy_python(contents: Path, arch: str, wheel: Path) -> Path:
    """Copy the runtime and install Squint + dependencies as prebuilt wheels for arch."""
    target = contents / "Resources" / f"python-{arch}"
    source = standalone_python(arch)

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
    site = next(target.glob("lib/python3.*/site-packages"))
    run("uv", "pip", "install", "--target", site, "--no-cache", "--only-binary", ":all:",
        "--python-platform", f"{UV_ARCH[arch]}-apple-darwin", "--python-version", PYTHON_VERSION,
        wheel)  # fmt: skip
    # Precompile so nothing writes .pyc into the signed bundle. Bytecode doesn't depend
    # on the CPU, so the build machine's Python of the same version can do it.
    run(sys.executable, "-m", "compileall", "-q", "-j0", target / "lib")
    return target / "bin" / "python3"


# MARK: Signing


def macho_files(root: Path) -> list[Path]:
    found = []
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            with open(path, "rb") as f:
                if f.read(4) in MACHO_MAGIC:
                    found.append(path)
    return found


def sign(identity: str) -> None:
    """Sign every binary inside-out, then the app. Developer ID gets the hardened runtime."""
    release = identity != "-"
    flags = ["--force", "--sign", identity]
    if release:
        flags += ["--options", "runtime", "--timestamp"]
    main_executable = APP / "Contents" / "MacOS" / "Squint"
    inner = [p for p in macho_files(APP) if p != main_executable]
    for path in sorted(inner, key=lambda p: len(p.parts), reverse=True):
        run("codesign", *flags, path, capture_output=True)
    run("codesign", *flags, APP)
    run("codesign", "--verify", "--deep", "--strict", APP)


def notarize(path: Path, profile: str) -> None:
    run("xcrun", "notarytool", "submit", path, "--keychain-profile", profile, "--wait")


def staple(path: Path) -> None:
    run("xcrun", "stapler", "staple", path)


# MARK: DMG


def build_dmg(identity: str) -> Path:
    dmg = DIST / "Squint.dmg"
    dmg.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "Squint"
        stage.mkdir()
        shutil.copytree(APP, stage / "Squint.app", symlinks=True)
        (stage / "Applications").symlink_to("/Applications")
        run("hdiutil", "create", "-volname", "Squint", "-srcfolder", stage,
            "-ov", "-format", "UDZO", dmg, capture_output=True)  # fmt: skip
    if identity != "-":
        run("codesign", "--force", "--sign", identity, "--timestamp", dmg)
    return dmg


def check_not_running() -> None:
    running = subprocess.run(
        ["pgrep", "-f", str(APP)], check=False, capture_output=True, text=True
    )
    if running.stdout.strip():
        raise SystemExit(
            f"Squint is running from {APP}; quit it first (menu bar → Quit)."
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sign", default="-", help='codesign identity ("-" = ad hoc)')
    parser.add_argument(
        "--notarize", metavar="PROFILE", help="notarytool keychain profile"
    )
    parser.add_argument(
        "--out", type=Path, default=ROOT / "dist", help="output folder (default dist/)"
    )
    args = parser.parse_args()
    global DIST, APP
    DIST, APP = args.out.resolve(), args.out.resolve() / "Squint.app"
    if args.notarize and args.sign == "-":
        parser.error("--notarize needs --sign with a Developer ID Application identity")

    check_not_running()
    if APP.exists():
        shutil.rmtree(APP)
    contents = APP / "Contents"
    build_swift(contents)
    build_icon(contents)
    write_info_plist(contents)
    with tempfile.TemporaryDirectory() as tmp:
        wheel = build_wheel(Path(tmp))
        pythons = {arch: copy_python(contents, arch, wheel) for arch in ARCHS}
    native = platform.machine()
    if (
        native in pythons
    ):  # the bundle is self-contained (the other arch can't run here)
        run(pythons[native], "-c", "import squint.cli, PIL, requests")

    sign(args.sign)
    if args.notarize:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "Squint.zip"
            run("ditto", "-c", "-k", "--keepParent", APP, archive)
            notarize(archive, args.notarize)
        staple(APP)
    dmg = build_dmg(args.sign)
    if args.notarize:
        notarize(dmg, args.notarize)
        staple(dmg)

    size = run("du", "-sh", APP, capture_output=True, text=True).stdout.split()[0]
    dmg_size = run("du", "-sh", dmg, capture_output=True, text=True).stdout.split()[0]
    kind = (
        "notarized"
        if args.notarize
        else ("signed" if args.sign != "-" else "ad-hoc signed")
    )
    print(f"\nbuilt {APP} ({size}) and {dmg} ({dmg_size}), {kind}, {' + '.join(ARCHS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
