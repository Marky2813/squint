import random

import pytest
from PIL import Image, ImageDraw, ImageFont

from squint.core.redact import (
    STYLES,
    Rect,
    RedactionPlan,
    build_plan,
    contrast_colour,
    noise_patch,
    render,
    ring_colour,
    style_patch,
)
from squint.core.types import BBox

BOX = Rect(40, 30, 360, 70)


def screenshot_with(text: str) -> Image.Image:
    image = Image.new("RGB", (400, 100), (250, 250, 250))
    ImageDraw.Draw(image).text(
        (45, 35), text, fill=(20, 20, 20), font=ImageFont.load_default(size=24)
    )
    return image


def crop(image: Image.Image, rect: Rect) -> bytes:
    return image.crop((rect.left, rect.top, rect.right, rect.bottom)).tobytes()


@pytest.mark.parametrize("style", STYLES)
def test_box_pixels_do_not_depend_on_the_secret(style):
    plan = RedactionPlan((BOX,))
    a = render(screenshot_with("FAKE-secret-AAAA1111"), plan, style, seed=7)
    b = render(screenshot_with("FAKE-other-ZZZZ9999"), plan, style, seed=7)
    assert crop(a, BOX) == crop(b, BOX)


@pytest.mark.parametrize("style", STYLES)
def test_pixels_outside_the_box_are_untouched(style):
    original = screenshot_with("FAKE-secret-AAAA1111")
    out = render(original, RedactionPlan((Rect(40, 30, 200, 70),)), style, seed=1)
    right_half = Rect(200, 0, 400, 100)
    assert crop(out, right_half) == crop(original, right_half)


def test_render_does_not_modify_input():
    original = screenshot_with("FAKE-secret")
    before = original.tobytes()
    render(original, RedactionPlan((BOX,)), seed=1)
    assert original.tobytes() == before


def test_render_rejects_unknown_style():
    with pytest.raises(ValueError):
        render(screenshot_with("x"), RedactionPlan(()), "swirl")


def test_render_with_empty_plan_returns_identical_copy():
    original = screenshot_with("FAKE")
    assert render(original, RedactionPlan(())).tobytes() == original.tobytes()


def test_build_plan_rounds_outward_and_clamps():
    plan = build_plan(
        [BBox(-2.5, 10.2, 20.0, 5.5), BBox(390.4, 90.0, 50, 50)], (400, 100)
    )
    assert plan.rects == (Rect(0, 10, 18, 16), Rect(390, 90, 400, 100))


def test_build_plan_drops_boxes_outside_image():
    assert build_plan([BBox(500, 500, 10, 10)], (400, 100)).rects == ()


def test_ring_colour_ignores_pixels_inside_rect():
    image = Image.new("RGB", (20, 20), (200, 100, 50))
    image.paste((0, 0, 0), (5, 5, 15, 15))
    assert ring_colour(image, Rect(5, 5, 15, 15)) == (200, 100, 50)


def test_ring_colour_for_full_image_box_falls_back_to_white():
    assert ring_colour(Image.new("RGB", (4, 4)), Rect(0, 0, 4, 4)) == (255, 255, 255)


def test_contrast_colour_darkens_light_and_lightens_dark():
    assert sum(contrast_colour((240, 240, 240))) < 300
    assert sum(contrast_colour((10, 10, 10))) > 450


def test_noise_patch_is_seeded():
    a = noise_patch((10, 4), (255, 255, 255), (0, 0, 0), random.Random(3))
    b = noise_patch((10, 4), (255, 255, 255), (0, 0, 0), random.Random(3))
    assert a.size == (10, 4)
    assert a.tobytes() == b.tobytes()


def test_style_patch_solid_is_uniform():
    patch = style_patch(Image.new("RGB", (8, 8), (9, 9, 9)), "solid", (1, 2, 3))
    assert patch.getcolors() == [(64, (1, 2, 3))]


def test_style_patch_pixelate_makes_blocks():
    patch = noise_patch((40, 20), (255, 255, 255), (0, 0, 0), random.Random(0))
    out = style_patch(patch, "pixelate", (0, 0, 0))
    assert out.getpixel((0, 0)) == out.getpixel((3, 3))
