"""Review state for one screenshot: flagged findings, drawn boxes, and the export."""

from dataclasses import asdict
from pathlib import Path

from PIL import Image

from squint.core.pipeline import Analysis, mask
from squint.core.redact import STYLES, RedactionPlan, build_plan, render
from squint.core.types import BBox

# Boxes the user draws are always opaque: they were chosen by hand, so hide them fully.
DRAWN_STYLE = "solid"


class ReviewSession:
    def __init__(self, image_path: Path, analysis: Analysis, source: str = "file"):
        """source is "file" (screenshot saved to disk) or "clipboard"."""
        self.image_path = image_path
        self.analysis = analysis
        self.source = source
        self.style = "pixelate"
        self.flagged = {f.id: f.flagged for f in analysis.findings}
        self.boxes: dict[int, BBox] = {}
        self.next_box_id = 0
        with Image.open(image_path) as image:
            self.size = image.size

    def to_json(self) -> dict:
        """Everything the review UI needs. Raw values never leave this object."""
        return {
            "image": {
                "name": self.image_path.name,
                "width": self.size[0],
                "height": self.size[1],
            },
            "source": self.source,
            "classifier_offline": self.analysis.classifier_offline,
            "style": self.style,
            "styles": list(STYLES),
            "findings": [
                {
                    "id": f.id,
                    "rule": f.rule,
                    "tier": f.tier,
                    "preview": mask(f.value),
                    "bbox": asdict(f.bbox) if f.bbox else None,
                    "flagged": self.flagged[f.id],
                }
                for f in self.analysis.findings
            ],
            "boxes": [{"id": i, **asdict(b)} for i, b in self.boxes.items()],
        }

    def toggle(self, finding_id: int) -> bool:
        """Flip a finding between flagged and dismissed; returns the new state."""
        if finding_id not in self.flagged:
            raise KeyError(finding_id)
        self.flagged[finding_id] = not self.flagged[finding_id]
        return self.flagged[finding_id]

    def add_box(self, box: BBox) -> int:
        """Hide a region the user drew; returns its id. Clamped to the image."""
        rect = build_plan([box], self.size).rects
        if not rect:
            raise ValueError("box is outside the image")
        r = rect[0]
        box_id = self.next_box_id
        self.next_box_id += 1
        self.boxes[box_id] = BBox(r.left, r.top, r.width, r.height)
        return box_id

    def remove_box(self, box_id: int) -> None:
        if box_id not in self.boxes:
            raise KeyError(box_id)
        del self.boxes[box_id]

    def plan(self) -> RedactionPlan:
        detected = [
            f.bbox
            for f in self.analysis.findings
            if self.flagged[f.id] and f.bbox is not None
        ]
        drawn = build_plan(list(self.boxes.values()), self.size, DRAWN_STYLE)
        return RedactionPlan(build_plan(detected, self.size).rects + drawn.rects)

    def set_style(self, style: str) -> None:
        if style not in STYLES:
            raise ValueError(f"unknown style {style!r}")
        self.style = style

    def output_path(self) -> Path:
        return self.image_path.with_name(f"{self.image_path.stem}.redacted.png")

    def export(self, style: str | None = None) -> Path:
        """Write <name>.redacted.png next to the original. The original is never touched."""
        style = style or self.style
        with Image.open(self.image_path) as image:
            redacted = render(image, self.plan(), style)
        out = self.output_path()
        redacted.save(out)  # new image object: no EXIF or other metadata carried over
        return out
