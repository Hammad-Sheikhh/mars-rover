"""Mission control: a page in the laptop's browser to watch the run and press STOP.

GET  /        the page (mission_control.html)
GET  /state   everything the page shows, as JSON
GET  /photo   the latest camera photo
POST /stop    stop the rover and pause Jev
POST /resume  let Jev drive again

Only this laptop can open it: it listens on 127.0.0.1, answers only to the names
127.0.0.1 and localhost, and STOP/Resume need the X-Mission-Control header, which
a page from another website can't send without our permission (we never give it).

The web server runs in its own thread. Every question it has for the station is
handed to the station's asyncio loop, so the two never touch the same data at once.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .station import Station

HOST = "127.0.0.1"
HEADER = "X-Mission-Control"
ALLOWED_HOSTS = ("127.0.0.1", "localhost")


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows this option would let a second program open the same port.
    allow_reuse_address = os.name != "nt"


class MissionControl:
    def __init__(self, station: Station, loop: asyncio.AbstractEventLoop, port: int = 8000):
        self.station = station
        self.loop = loop
        self.port = port
        self.page = files(__package__).joinpath("mission_control.html").read_bytes()
        self._server: _Server | None = None

    def start(self) -> str:
        """Start serving in a background thread. Raises OSError if the port is taken."""
        self._server = _Server((HOST, self.port), _handler(self))
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return f"http://{HOST}:{self.port}"

    def close(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def call(self, coro: Any) -> Any:
        """Run a station coroutine on the station's loop and wait for the answer."""
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout=3)


def _handler(mc: MissionControl):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # keep the terminal for the run itself
            pass

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, body: dict[str, Any]) -> None:
            self._send(code, json.dumps(body, default=str).encode(), "application/json")

        def _host_ok(self) -> bool:
            host = self.headers.get("Host", "").rsplit(":", 1)[0].lower()
            return host in ALLOWED_HOSTS

        def do_GET(self):  # noqa: N802
            if not self._host_ok():
                self._json(403, {"error": "open mission control at http://127.0.0.1"})
                return
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._send(200, mc.page, "text/html; charset=utf-8")
            elif path == "/state":
                try:
                    self._json(200, mc.call(mc.station.snapshot()))
                except Exception as e:  # the station is shutting down
                    self._json(503, {"error": f"station not answering: {e}"})
            elif path == "/photo":
                photo = mc.station.board.photo
                if photo is None:
                    self._json(404, {"error": "no photo yet"})
                else:
                    self._send(200, photo, "image/jpeg")
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if not self._host_ok() or self.headers.get(HEADER) != "1":
                self._json(403, {"error": "only the mission control page can do this"})
                return
            path = self.path.split("?", 1)[0]
            if path == "/stop":
                action = mc.station.pause
            elif path == "/resume":
                action = mc.station.resume
            else:
                self._json(404, {"error": "not found"})
                return
            try:
                mc.call(action())
            except Exception as e:
                self._json(503, {"error": f"station not answering: {e}"})
                return
            self._json(200, {"paused": mc.station.paused})

    return Handler
