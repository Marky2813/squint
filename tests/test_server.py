import http.client
import json

import pytest
from PIL import Image

from squint.core.pipeline import Analysis, Finding
from squint.core.review import ReviewSession
from squint.core.types import BBox
from squint.server import ReviewServer

SECRET = "FAKEsecretValue123"


@pytest.fixture
def server(tmp_path):
    path = tmp_path / "shot.png"
    Image.new("RGB", (100, 50), "white").save(path)
    analysis = Analysis(
        (Finding(0, "stripe_key", "sensitive", SECRET, BBox(10, 10, 30, 10), True),),
        False,
    )
    exported = []
    srv = ReviewServer(on_export=exported.append)
    srv.show(ReviewSession(path, analysis))
    srv.start()
    srv.exported = exported
    yield srv
    srv.stop()


def request(srv, method, path, body=None, token=None, host=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    sep = "&" if "?" in path else "?"
    url = f"{path}{sep}t={srv.token if token is None else token}"
    headers = {"Host": host or f"127.0.0.1:{srv.port}"}
    conn.request(method, url, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data


def test_url_is_loopback_with_token(server):
    assert server.url == f"http://127.0.0.1:{server.port}/?t={server.token}"
    assert len(server.token) >= 32


@pytest.mark.parametrize("path", ["/", "/api/findings", "/api/image"])
def test_wrong_token_is_rejected(server, path):
    status, body = request(server, "GET", path, token="nope")
    assert status == 403
    assert SECRET.encode() not in body


def test_foreign_host_header_is_rejected(server):
    status, _ = request(
        server, "GET", "/api/findings", host=f"evil.example:{server.port}"
    )
    assert status == 403


def test_post_with_wrong_token_does_not_export(server):
    status, _ = request(server, "POST", "/api/export", body="{}", token="nope")
    assert status == 403
    assert server.exported == []


def test_page_and_findings(server):
    status, page = request(server, "GET", "/")
    assert status == 200 and b"<title>Squint review</title>" in page
    status, body = request(server, "GET", "/api/findings")
    data = json.loads(body)
    assert status == 200
    assert data["findings"][0]["preview"] == "FAKE…123"
    assert SECRET.encode() not in body


def test_image_is_served(server):
    status, body = request(server, "GET", "/api/image")
    assert status == 200 and body.startswith(b"\x89PNG")


def test_toggle(server):
    status, body = request(server, "POST", "/api/findings/0/toggle", body="{}")
    assert status == 200 and json.loads(body) == {"id": 0, "flagged": False}
    status, _ = request(server, "POST", "/api/findings/9/toggle", body="{}")
    assert status == 404


def test_export_writes_file_and_calls_hook(server):
    status, body = request(server, "POST", "/api/export", body='{"style": "blur"}')
    data = json.loads(body)
    assert status == 200 and data["copied"] is True
    assert data["path"].endswith("shot.redacted.png")
    assert [str(p) for p in server.exported] == [data["path"]]


def test_export_rejects_unknown_style(server):
    status, _ = request(server, "POST", "/api/export", body='{"style": "swirl"}')
    assert status == 400


def test_export_reports_clipboard_failure(server):
    def broken(path):
        raise OSError("no clipboard")

    server.on_export = broken
    status, body = request(server, "POST", "/api/export", body="{}")
    assert status == 200 and json.loads(body)["copied"] is False


def test_no_session_returns_404(tmp_path):
    srv = ReviewServer()
    srv.start()
    try:
        status, _ = request(srv, "GET", "/api/findings")
        assert status == 404
    finally:
        srv.stop()


def test_version_tracks_sessions_and_page_presence(server, tmp_path):
    assert not server.page_open()
    status, body = request(server, "GET", "/api/version")
    assert status == 200 and json.loads(body) == {"version": 1}
    assert server.page_open()
    server.show(server.session)
    assert json.loads(request(server, "GET", "/api/version")[1]) == {"version": 2}


def test_version_requires_token(server):
    status, _ = request(server, "GET", "/api/version", token="nope")
    assert status == 403
    assert not server.page_open()


@pytest.fixture
def live_server(tmp_path):
    path = tmp_path / "live.png"
    Image.new("RGB", (100, 50), "white").save(path)
    analysis = Analysis(
        (Finding(0, "stripe_key", "sensitive", SECRET, BBox(10, 10, 30, 10), True),),
        False,
    )
    exported = []
    srv = ReviewServer(on_export=exported.append, live=True)
    srv.exported = exported
    srv.show(ReviewSession(path, analysis))
    srv.start()
    yield srv
    srv.stop()


def test_live_show_copies_immediately(live_server):
    assert [p.name for p in live_server.exported] == ["live.redacted.png"]


def test_live_toggle_recopies(live_server):
    status, body = request(live_server, "POST", "/api/findings/0/toggle", body="{}")
    assert status == 200 and json.loads(body)["copied"] is True
    assert len(live_server.exported) == 2


def test_live_style_change_recopies(live_server):
    status, body = request(live_server, "POST", "/api/style", body='{"style": "solid"}')
    assert status == 200 and json.loads(body)["copied"] is True
    assert live_server.session.style == "solid"
    assert len(live_server.exported) == 2


def test_style_change_without_live_does_not_export(server):
    status, body = request(server, "POST", "/api/style", body='{"style": "blur"}')
    assert status == 200 and json.loads(body) == {"style": "blur"}
    assert server.exported == []


def test_toggle_without_live_does_not_export(server):
    request(server, "POST", "/api/findings/0/toggle", body="{}")
    assert server.exported == []


def test_export_uses_session_style_by_default(server):
    request(server, "POST", "/api/style", body='{"style": "solid"}')
    status, body = request(server, "POST", "/api/export", body="{}")
    assert status == 200 and json.loads(body)["style"] == "solid"


BOX = '{"x": 50, "y": 20, "width": 20, "height": 10}'


def test_live_draw_box_recopies_and_lists_it(live_server):
    status, body = request(live_server, "POST", "/api/boxes", body=BOX)
    assert status == 200 and json.loads(body) == {"id": 0, "copied": True}
    assert len(live_server.exported) == 2
    _, findings = request(live_server, "GET", "/api/findings")
    assert json.loads(findings)["boxes"][0]["x"] == 50


def test_live_remove_box_recopies(live_server):
    request(live_server, "POST", "/api/boxes", body=BOX)
    status, body = request(live_server, "POST", "/api/boxes/0/delete", body="{}")
    assert status == 200 and json.loads(body)["copied"] is True
    assert live_server.session.boxes == {}
    assert len(live_server.exported) == 3


@pytest.mark.parametrize(
    "body",
    [
        '{"x": 1}',
        '{"x": "a", "y": 0, "width": 1, "height": 1}',
        BOX.replace("50", "500"),
    ],
)
def test_invalid_box_is_rejected(server, body):
    status, _ = request(server, "POST", "/api/boxes", body=body)
    assert status == 400


def test_remove_unknown_box_is_404(server):
    status, _ = request(server, "POST", "/api/boxes/7/delete", body="{}")
    assert status == 404


def test_redacted_view_serves_current_redaction(server):
    _, original = request(server, "GET", "/api/image")
    status, redacted = request(server, "GET", "/api/image?view=redacted")
    assert status == 200 and redacted.startswith(b"\x89PNG") and redacted != original
