"""Command-line entry point: squint check <image> | squint watch."""

import argparse
import sys
import time
from pathlib import Path

from squint import watch
from squint.core.classify import OllamaClassifier
from squint.core.pipeline import analyze, mask
from squint.core.redact import STYLES
from squint.core.review import ReviewSession
from squint.platforms.macos.desktop import MacDesktop
from squint.platforms.macos.ocr import MacOcrEngine


def check(path: Path, style: str) -> int:
    ocr = MacOcrEngine()
    classifier = OllamaClassifier()
    if not classifier.warm_up():
        print("warning: Gemma unavailable; every ambiguous match will be flagged")

    started = time.perf_counter()
    lines = ocr.recognize(path)
    ocr_done = time.perf_counter()
    result = analyze(lines, classifier)
    done = time.perf_counter()

    for f in result.findings:
        status = "FLAG" if f.flagged else "ok  "
        print(f"{status} {f.rule:<16} {f.tier:<9} {mask(f.value)}")
    if result.classifier_offline:
        print("classifier offline: review carefully")
    print(
        f"timing: ocr {ocr_done - started:.2f}s, "
        f"classify {done - ocr_done:.2f}s, total {done - started:.2f}s"
    )

    if not result.flagged:
        print("nothing to redact")
        return 0
    print(f"wrote {ReviewSession(path, result).export(style)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="squint")
    sub = parser.add_subparsers(dest="command", required=True)
    check_cmd = sub.add_parser("check", help="scan one screenshot")
    check_cmd.add_argument("image", type=Path)
    check_cmd.add_argument("--style", choices=STYLES, default="pixelate")
    watch_cmd = sub.add_parser("watch", help="scan new screenshots as they appear")
    watch_cmd.add_argument(
        "--quiet", action="store_true", help="no notification for clean screenshots"
    )
    args = parser.parse_args(argv)
    if args.command == "watch":
        watch.run(MacOcrEngine(), MacDesktop(), quiet=args.quiet)
        return 0
    return check(args.image, args.style)


if __name__ == "__main__":
    sys.exit(main())
