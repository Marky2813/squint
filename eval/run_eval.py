"""Score the full pipeline (real OCR + local Gemma) against eval/labels.json.

    uv run python eval/run_eval.py              # tuning set
    uv run python eval/run_eval.py --held-out   # the 5 held-out screenshots (report only)

Metrics:
  recall      sensitive items that were hidden            (target >= 95%)
  precision   hidden findings that were really sensitive  (target >= 70%)
  coverage    sensitive items whose pixels are fully covered by redaction boxes
  readable    keys next to secrets left readable (box covers < 25% of the key)
  latency     OCR + classification per screenshot (target ~2 s)

Items are matched to findings by text. Values are never printed in full.
"""

import argparse
import difflib
import json
import statistics
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

from squint.core.classify import OllamaClassifier
from squint.core.pipeline import Finding, analyze, mask
from squint.platforms.macos.ocr import MacOcrEngine

HERE = Path(__file__).resolve().parent
FULLY_COVERED = 0.99
READABLE = 0.25


def normalise(text: str) -> str:
    return "".join(text.split()).lower()


def matches(item: dict, finding: Finding) -> bool:
    """Same text, allowing for containment and OCR misreads (l/1, O/0)."""
    a, b = normalise(item["value"]), normalise(finding.value)
    if len(b) < 4:
        return False
    if a in b or b in a:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.85


def covered_fraction(bbox: list[float], boxes: list, size: tuple[int, int]) -> float:
    """Share of bbox's pixels inside the union of boxes."""
    x, y, w, h = bbox
    w, h = min(w, size[0] - x), min(h, size[1] - y)  # only the part inside the image
    if w <= 0 or h <= 0:
        return 1.0
    mask_image = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask_image)
    for b in boxes:
        draw.rectangle((b.x, b.y, b.x + b.width - 1, b.y + b.height - 1), fill=255)
    region = mask_image.crop((int(x), int(y), int(x + w), int(y + h)))
    return region.histogram()[255] / (region.width * region.height)


def score(name: str, items: list[dict], findings: tuple[Finding, ...], size) -> dict:
    flagged = [f for f in findings if f.flagged]
    boxes = [f.bbox for f in flagged if f.bbox is not None]
    result = {"tp": 0, "fn": [], "fp": [], "neg_hidden": [], "covered": 0, "uncovered": [],
              "keys": 0, "keys_readable": 0, "boxed": 0}  # fmt: skip
    for item in items:
        hit = any(matches(item, f) for f in flagged)
        if item["sensitive"]:
            if hit:
                result["tp"] += 1
            else:
                result["fn"].append(f"{item['category']} {mask(item['value'])}")
            if "bbox" in item:
                result["boxed"] += 1
                share = covered_fraction(item["bbox"], boxes, size)
                if share >= FULLY_COVERED:
                    result["covered"] += 1
                else:
                    result["uncovered"].append(
                        f"{item['category']} {share:.0%} covered"
                    )
        elif item.get("keep_visible") and "bbox" in item:
            result["keys"] += 1
            if covered_fraction(item["bbox"], boxes, size) < READABLE:
                result["keys_readable"] += 1
        elif hit:
            result["neg_hidden"].append(f"{item['category']} {mask(item['value'])}")
    sensitive = [i for i in items if i["sensitive"]]
    for f in flagged:
        if not any(matches(i, f) for i in sensitive):
            result["fp"].append(f"{f.rule} {mask(f.value)}")
    return result


def pct(numerator: int, denominator: int) -> str:
    return (
        f"{numerator / denominator:.0%} ({numerator}/{denominator})"
        if denominator
        else "n/a"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--held-out", action="store_true", help="score the held-out set"
    )
    parser.add_argument("--labels", type=Path, default=HERE / "labels.json")
    args = parser.parse_args()

    labels = json.loads(args.labels.read_text())["screenshots"]
    chosen = {n: s for n, s in labels.items() if s["held_out"] == args.held_out}
    ocr, classifier = MacOcrEngine(), OllamaClassifier()
    if not classifier.warm_up():
        print(
            "warning: Gemma unavailable; results reflect the fail-safe (flag everything)"
        )
    ocr.recognize(HERE / "fixtures" / next(iter(chosen)))  # pay Vision's first-use cost

    totals = {"tp": 0, "fn": 0, "fp": 0, "neg_hidden": 0, "covered": 0, "boxed": 0,
              "keys": 0, "keys_readable": 0}  # fmt: skip
    latencies = []
    for name, shot in sorted(chosen.items()):
        path = HERE / "fixtures" / name
        started = time.perf_counter()
        result = analyze(ocr.recognize(path), classifier)
        latencies.append(time.perf_counter() - started)
        with Image.open(path) as image:
            r = score(name, shot["items"], result.findings, image.size)
        for key in totals:
            totals[key] += len(r[key]) if isinstance(r[key], list) else r[key]
        problems = r["fn"] + r["fp"] + r["neg_hidden"] + r["uncovered"]
        status = "ok " if not problems else "!! "
        print(f"{status}{name:<34} {latencies[-1]:.2f}s")
        for label, entries in (("missed", r["fn"]), ("over-flagged", r["fp"]),
                               ("negative hidden", r["neg_hidden"]),
                               ("partly visible", r["uncovered"])):  # fmt: skip
            for entry in entries:
                print(f"      {label}: {entry}")

    flagged = totals["tp"] + totals["fp"]
    sensitive = totals["tp"] + totals["fn"]
    print(
        f"\n{'held-out' if args.held_out else 'tuning'} set: {len(chosen)} screenshots"
    )
    print(f"  recall     {pct(totals['tp'], sensitive)}   target >= 95%")
    print(f"  precision  {pct(totals['tp'], flagged)}   target >= 70%")
    print(f"  coverage   {pct(totals['covered'], totals['boxed'])}   fully hidden")
    print(
        f"  readable   {pct(totals['keys_readable'], totals['keys'])}   keys left readable"
    )
    print(f"  negatives hidden: {totals['neg_hidden']}")
    print(
        f"  latency    median {statistics.median(latencies):.2f}s, "
        f"max {max(latencies):.2f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
