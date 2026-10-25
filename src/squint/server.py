"""Localhost JSON API + HTML page for reviewing one screenshot at a time.

Every request must carry the per-run token (?t=...) and a loopback Host header, so other
web pages (and DNS-rebinding tricks) can't read the screenshot or trigger an export.
"""

import json
import re
import secrets
import threading
import time
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from squint.core.redact import STYLES
from squint.core.review import ReviewSession
from squint.core.types import BBox

PAGE = Path(__file__).with_name("web") / "review.html"
TOGGLE = re.compile(r"^/api/findings/(\d+)/toggle$")
REMOVE_BOX = re.compile(r"^/api/boxes/(\d+)/delete$")
# The page polls /api/version every second; silence for longer means no tab is open.
PAGE_TIMEOUT_SECONDS = 3.0


class ReviewServer:
    def __init__(
        self,
        on_export: Callable[[Path], None] | None = None,
        port: int = 0,
        live: bool = False,
    ):
        """on_export(path) runs after each export; it should raise OSError on failure.

        With live=True, every new session and every change re-exports and calls on_export,
        so the clipboard always holds the current redaction without an Export click.
        """
        self.live = live
        self.token = secrets.token_urlsafe(24)
        self.session: ReviewSession | None = None
        self.on_export = on_export
        self.lock = threading.Lock()
        self.version = 0
        self.last_poll = float("-inf")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), _handler_for(self))
        self.port = self.httpd.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?t={self.token}"

    def show(self, session: ReviewSession) -> None:
        with self.lock:
            self.session = session
            self.version += 1
            if self.live:
                self.export_and_copy(session)

    def export_and_copy(self, session: ReviewSession) -> tuple[Path, bool]:
        out = session.export()
        if self.on_export is None:
            return out, False
        try:
            self.on_export(out)
        except OSError:  # clipboard failure must not lose the export
            return out, False
        return out, True

    def page_open(self) -> bool:
        return time.monotonic() - self.last_poll < PAGE_TIMEOUT_SECONDS

    def start(self) -> None:
        threading.Thread(
            target=self.httpd.serve_forever, args=(0.05,), daemon=True
        ).start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def _handler_for(server: ReviewServer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # never log URLs (they carry the token)
            pass

        def _authorised(self) -> bool:
            hosts = {f"127.0.0.1:{server.port}", f"localhost:{server.port}"}
            token = parse_qs(urlparse(self.path).query).get("t", [""])[0]
            return self.headers.get("Host") in hosts and secrets.compare_digest(
                token, server.token
            )

        def _send(self, status, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, status=HTTPStatus.OK) -> None:
            self._send(status, json.dumps(data).encode(), "application/json")

        def _error(self, status, message: str) -> None:
            self._json({"error": message}, status)

        def _recopy(self, session: ReviewSession) -> dict:
            """In live mode every change goes straight to the clipboard."""
            if not server.live:
                return {}
            return {"copied": server.export_and_copy(session)[1]}

        def do_GET(self):
            if not self._authorised():
                return self._error(HTTPStatus.FORBIDDEN, "forbidden")
            path = urlparse(self.path).path
            if path == "/api/version":
                server.last_poll = time.monotonic()
                return self._json({"version": server.version})
            if path == "/":
                return self._send(
                    HTTPStatus.OK, PAGE.read_bytes(), "text/html; charset=utf-8"
                )
            with server.lock:
                session = server.session
            if session is None:
                return self._error(HTTPStatus.NOT_FOUND, "no screenshot under review")
            if path == "/api/findings":
                return self._json(session.to_json())
            if path == "/api/image":
                view = parse_qs(urlparse(self.path).query).get("view", [""])[0]
                if view == "redacted":  # exactly what is (or would be) on the clipboard
                    with server.lock:
                        image = session.export()
                else:
                    image = session.image_path
                return self._send(HTTPStatus.OK, image.read_bytes(), "image/png")
            return self._error(HTTPStatus.NOT_FOUND, "not found")

        def do_POST(self):
            if not self._authorised():
                return self._error(HTTPStatus.FORBIDDEN, "forbidden")
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._error(HTTPStatus.BAD_REQUEST, "invalid json")
            with server.lock:
                session = server.session
                if session is None:
                    return self._error(
                        HTTPStatus.NOT_FOUND, "no screenshot under review"
                    )
                if match := TOGGLE.match(path):
                    try:
                        flagged = session.toggle(int(match.group(1)))
                    except KeyError:
                        return self._error(HTTPStatus.NOT_FOUND, "unknown finding")
                    reply = {"id": int(match.group(1)), "flagged": flagged}
                    return self._json(reply | self._recopy(session))
                if path == "/api/boxes":
                    try:
                        box = BBox(
                            *(float(body[k]) for k in ("x", "y", "width", "height"))
                        )
                        box_id = session.add_box(box)
                    except (KeyError, TypeError, ValueError):
                        return self._error(HTTPStatus.BAD_REQUEST, "invalid box")
                    return self._json({"id": box_id, **self._recopy(session)})
                if match := REMOVE_BOX.match(path):
                    try:
                        session.remove_box(int(match.group(1)))
                    except KeyError:
                        return self._error(HTTPStatus.NOT_FOUND, "unknown box")
                    return self._json(
                        {"id": int(match.group(1)), **self._recopy(session)}
                    )
                if path in ("/api/style", "/api/export"):
                    style = body.get("style", session.style)
                    if style not in STYLES:
                        return self._error(HTTPStatus.BAD_REQUEST, "unknown style")
                    session.set_style(style)
                    if path == "/api/style" and not server.live:
                        return self._json({"style": style})
                    out, copied = server.export_and_copy(session)
                    return self._json(
                        {"style": style, "path": str(out), "copied": copied}
                    )
            return self._error(HTTPStatus.NOT_FOUND, "not found")

    return Handler
