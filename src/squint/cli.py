"""Command-line entry point: squint check <image>."""

import argparse
import sys
import time
from pathlib import Path

from PIL import Image

from squint.core.classify import OllamaClassifier
from squint.core.pipeline import analyze, mask
from squint.core.redact import STYLES, build_plan, render
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

    boxes = [f.bbox for f in result.flagged if f.bbox is not None]
    if not boxes:
        print("nothing to redact")
        return 0
    with Image.open(path) as image:
        redacted = render(image, build_plan(boxes, image.size), style)
    out = path.with_name(f"{path.stem}.redacted.png")
    redacted.save(out)  # fresh image: no EXIF or other metadata carried over
    print(f"wrote {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="squint")
    sub = parser.add_subparsers(dest="command", required=True)
    check_cmd = sub.add_parser("check", help="scan one screenshot")
    check_cmd.add_argument("image", type=Path)
    check_cmd.add_argument("--style", choices=STYLES, default="pixelate")
    args = parser.parse_args(argv)
    return check(args.image, args.style)


if __name__ == "__main__":
    sys.exit(main())
