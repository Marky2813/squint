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
