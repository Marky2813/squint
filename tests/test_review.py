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
