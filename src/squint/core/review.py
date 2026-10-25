"""Review state for one screenshot: which findings are flagged, and the export."""

from dataclasses import asdict
from pathlib import Path

from PIL import Image

from squint.core.pipeline import Analysis, mask
from squint.core.redact import STYLES, build_plan, render


class ReviewSession:
    def __init__(self, image_path: Path, analysis: Analysis, source: str = "file"):
        """source is "file" (screenshot saved to disk) or "clipboard"."""
        self.image_path = image_path
        self.analysis = analysis
        self.source = source
        self.style = "pixelate"
        self.flagged = {f.id: f.flagged for f in analysis.findings}
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
        }

    def toggle(self, finding_id: int) -> bool:
        """Flip a finding between flagged and dismissed; returns the new state."""
        if finding_id not in self.flagged:
            raise KeyError(finding_id)
        self.flagged[finding_id] = not self.flagged[finding_id]
        return self.flagged[finding_id]

    def set_style(self, style: str) -> None:
        if style not in STYLES:
            raise ValueError(f"unknown style {style!r}")
        self.style = style

    def output_path(self) -> Path:
        return self.image_path.with_name(f"{self.image_path.stem}.redacted.png")

    def export(self, style: str | None = None) -> Path:
        """Write <name>.redacted.png next to the original. The original is never touched."""
        style = style or self.style
        boxes = [
            f.bbox
            for f in self.analysis.findings
            if self.flagged[f.id] and f.bbox is not None
        ]
        with Image.open(self.image_path) as image:
            redacted = render(image, build_plan(boxes, image.size), style)
        out = self.output_path()
        redacted.save(out)  # new image object: no EXIF or other metadata carried over
        return out
