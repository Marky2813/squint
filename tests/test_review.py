import json

import pytest
from PIL import Image

from squint.core.pipeline import Analysis, Finding
from squint.core.review import ReviewSession
from squint.core.types import BBox

SECRET = "FAKEsecretValue123"


@pytest.fixture
def session(tmp_path):
    path = tmp_path / "Screenshot 1.png"
    image = Image.new("RGB", (100, 50), (240, 240, 240))
    image.paste((0, 0, 0), (10, 10, 40, 20))
    image.paste((0, 0, 0), (60, 30, 90, 40))
    image.save(path)
    analysis = Analysis(
        findings=(
            Finding(0, "stripe_key", "sensitive", SECRET, BBox(10, 10, 30, 10), True),
            Finding(1, "email", "ambiguous", "a@b.co", BBox(60, 30, 30, 10), False),
            Finding(2, "jwt", "sensitive", SECRET, None, True),
        ),
        classifier_offline=False,
    )
    return ReviewSession(path, analysis)


def test_to_json_never_contains_raw_values(session):
    data = session.to_json()
    assert SECRET not in json.dumps(data)
    assert data["findings"][0]["preview"] == "FAKE…123"


def test_to_json_shape(session):
    data = session.to_json()
    assert data["image"] == {"name": "Screenshot 1.png", "width": 100, "height": 50}
    assert data["classifier_offline"] is False
    assert data["source"] == "file"
    assert data["style"] == "pixelate"
    assert "pixelate" in data["styles"]
    assert data["findings"][0]["bbox"] == {"x": 10, "y": 10, "width": 30, "height": 10}
    assert data["findings"][2]["bbox"] is None
    assert [f["flagged"] for f in data["findings"]] == [True, False, True]


def test_toggle_flips_state(session):
    assert session.toggle(1) is True
    assert session.toggle(1) is False


def test_toggle_unknown_id_raises(session):
    with pytest.raises(KeyError):
        session.toggle(99)


def test_export_redacts_only_flagged_boxes_and_keeps_original(session):
    original_bytes = session.image_path.read_bytes()
    out = session.export("solid")
    assert out.name == "Screenshot 1.redacted.png"
    assert session.image_path.read_bytes() == original_bytes
    with Image.open(out) as result:
        assert result.getpixel((20, 15)) != (0, 0, 0)  # flagged: replaced
        assert result.getpixel((70, 35)) == (0, 0, 0)  # dismissed: untouched


def test_export_after_toggle_includes_newly_flagged(session):
    session.toggle(1)
    with Image.open(session.export("solid")) as result:
        assert result.getpixel((70, 35)) != (0, 0, 0)


def test_export_strips_metadata(session):
    exif = Image.Exif()
    exif[0x010E] = "FAKE private description"  # ImageDescription
    with Image.open(session.image_path) as image:
        image.save(session.image_path, exif=exif, pnginfo=None)
    with Image.open(session.image_path) as image:
        assert "exif" in image.info
    with Image.open(session.export()) as result:
        assert "exif" not in result.info
        assert "FAKE private" not in str(result.info)


def test_set_style_changes_default_export_style(session):
    session.set_style("solid")
    assert session.to_json()["style"] == "solid"
    with Image.open(session.export()) as result:
        assert len(result.crop((10, 10, 40, 20)).getcolors()) == 1


def test_set_style_rejects_unknown(session):
    with pytest.raises(ValueError):
        session.set_style("swirl")


def test_drawn_box_is_listed_and_redacted_solid(session):
    box_id = session.add_box(BBox(60.4, 30, 30, 10))
    assert session.to_json()["boxes"] == [
        {"id": box_id, "x": 60, "y": 30, "width": 31, "height": 10}
    ]
    with Image.open(session.export()) as result:  # session style is pixelate
        assert len(result.crop((60, 30, 90, 40)).getcolors()) == 1


def test_drawn_box_is_clamped_and_outside_boxes_are_rejected(session):
    session.add_box(BBox(90, 40, 50, 50))
    assert session.to_json()["boxes"][0] == {
        "id": 0,
        "x": 90,
        "y": 40,
        "width": 10,
        "height": 10,
    }
    with pytest.raises(ValueError):
        session.add_box(BBox(200, 200, 5, 5))


def test_remove_box(session):
    box_id = session.add_box(BBox(60, 30, 30, 10))
    session.remove_box(box_id)
    assert session.to_json()["boxes"] == []
    with Image.open(session.export()) as result:
        assert result.getpixel((70, 35)) == (0, 0, 0)
    with pytest.raises(KeyError):
        session.remove_box(box_id)


def test_box_ids_are_never_reused(session):
    first = session.add_box(BBox(0, 0, 5, 5))
    session.remove_box(first)
    assert session.add_box(BBox(0, 0, 5, 5)) != first
