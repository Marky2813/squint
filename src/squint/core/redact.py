"""Irreversible redaction: destroy the pixels first, then apply the visual style.

Every style starts by replacing the box with random noise tinted from the pixels just
*outside* the box, so nothing inside the box survives to be de-pixelated or de-blurred.
"""

import math
import random
from dataclasses import dataclass

from PIL import Image, ImageFilter, ImageOps

from squint.core.types import BBox

STYLES = ("pixelate", "blur", "solid")
RING = 3


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


@dataclass(frozen=True)
class RedactionPlan:
    rects: tuple[Rect, ...]


def build_plan(boxes: list[BBox], image_size: tuple[int, int]) -> RedactionPlan:
    """Round each box outward to whole pixels and clamp it to the image."""
    width, height = image_size
    rects = []
    for b in boxes:
        rect = Rect(
            max(0, math.floor(b.x)),
            max(0, math.floor(b.y)),
            min(width, math.ceil(b.x + b.width)),
            min(height, math.ceil(b.y + b.height)),
        )
        if rect.width > 0 and rect.height > 0:
            rects.append(rect)
    return RedactionPlan(tuple(rects))


def ring_colour(image: Image.Image, rect: Rect) -> tuple[int, int, int]:
    """Mean colour of a thin ring of pixels around rect (never inside it)."""
    pixels = []
    for x in range(rect.left - RING, rect.right + RING):
        for y in range(rect.top - RING, rect.bottom + RING):
            inside = rect.left <= x < rect.right and rect.top <= y < rect.bottom
            if not inside and 0 <= x < image.width and 0 <= y < image.height:
                pixels.append(image.getpixel((x, y)))
    if not pixels:
        return (255, 255, 255)
    return tuple(sum(p[i] for p in pixels) // len(pixels) for i in range(3))


def contrast_colour(bg: tuple[int, int, int]) -> tuple[int, int, int]:
    light = sum(bg) / 3 > 128
    return tuple(int(c * 0.25) if light else int(c + (255 - c) * 0.75) for c in bg)


def noise_patch(
    size: tuple[int, int],
    bg: tuple[int, int, int],
    fg: tuple[int, int, int],
    rng: random.Random,
) -> Image.Image:
    grey = Image.frombytes("L", size, rng.randbytes(size[0] * size[1]))
    return ImageOps.colorize(grey, black=fg, white=bg)


def style_patch(
    patch: Image.Image, style: str, fg: tuple[int, int, int]
) -> Image.Image:
    w, h = patch.size
    if style == "solid":
        return Image.new("RGB", patch.size, fg)
    if style == "blur":
        return patch.filter(ImageFilter.GaussianBlur(radius=max(3, h / 3)))
    if style == "pixelate":
        block = max(4, h // 2)
        small = patch.resize(
            (max(1, w // block), max(1, h // block)), Image.Resampling.BOX
        )
        return small.resize(patch.size, Image.Resampling.NEAREST)
    raise ValueError(f"unknown style {style!r}; expected one of {STYLES}")


def render(
    image: Image.Image,
    plan: RedactionPlan,
    style: str = "pixelate",
    seed: int | None = None,
) -> Image.Image:
    """Return a redacted copy. The original image is never modified."""
    if style not in STYLES:
        raise ValueError(f"unknown style {style!r}; expected one of {STYLES}")
    source = image.convert("RGB")
    out = source.copy()
    rng = random.Random(seed)
    for rect in plan.rects:
        bg = ring_colour(source, rect)
        fg = contrast_colour(bg)
        patch = noise_patch((rect.width, rect.height), bg, fg, rng)
        out.paste(style_patch(patch, style, fg), (rect.left, rect.top))
    return out
