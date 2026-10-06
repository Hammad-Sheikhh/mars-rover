"""Fake rover + fake camera, so the Earth Station runs on any laptop with no hardware.

    python -m earth_station.sim            # rover on :8081, camera on :8082

It speaks the same protocol the real firmware will:
    rover  GET  /sensors/data     telemetry incl. distance_cm and mode
           POST /jev/cmd          {"seq","action","speed","duration_ms"} + X-Token
           GET  /mode?set=jev     pretend to press a button on the phone (jev | manual)
    camera GET  /capture          JPEG with the simulated scene in a comment segment
    both   GET  /id               {"board": "rover" | "camera", "firmware": "sim"}
"""

from __future__ import annotations

import argparse
import json
import random
import struct
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

ACTIONS = ("forward", "turn_left", "turn_right", "reverse", "stop")
REFLEX_STOP_CM = 20


class World:
    """A rover in a room full of boxes. Distance shrinks as it drives forward and
    jumps to a new value after a turn."""

    def __init__(self, mode: str = "jev", seed: int | None = None):
        self.rng = random.Random(seed)
        self.lock = threading.Lock()
        self.mode = mode
        self.distance_cm = 150.0
        self.clear_side = "right"
        self.last_event = "Nominal"
        self.last_seq: int | None = None
        self.moves = 0
        self.last_action: str | None = None

    def telemetry(self) -> dict[str, Any]:
        with self.lock:
            event, self.last_event = self.last_event, "Nominal"
            return {
                "ldrState": 0,
                "pressure": 1013.2,
                "altitude": 0.0,
                "temperature": round(24.0 + self.rng.uniform(-0.3, 0.3), 1),
                "humidity": 40,
                "pitch": round(self.rng.uniform(-3, 3), 1),
                "roll": round(self.rng.uniform(-3, 3), 1),
                "vibration": round(self.rng.uniform(0.01, 0.05), 3),
                "autonomous": 0,
                "distance_cm": round(self.distance_cm),
                "last_event": event,
                "mode": self.mode,
            }

    def scene(self) -> dict[str, Any]:
        with self.lock:
            d = self.distance_cm
            if d < 80:
                return {
                    "summary": f"Cardboard box about {d:.0f} cm ahead. "
                    f"Open floor to the {self.clear_side}.",
                    "obstacle_ahead": True,
                    "clear_side": self.clear_side,
                    "hazards": [],
                }
            return {
                "summary": "Open floor ahead, nothing close.",
                "obstacle_ahead": False,
                "clear_side": "both",
                "hazards": [],
            }

    def command(self, cmd: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            seq = cmd.get("seq")
            if self.mode != "jev":
                return {"ok": False, "seq": seq, "refused": "not_in_jev_mode"}
            action = cmd.get("action")
            if action not in ACTIONS:
                return {"ok": False, "seq": seq, "refused": "unknown_action"}
            if seq is not None and seq == self.last_seq:
                return {"ok": True, "seq": seq, "executed": "duplicate_ignored"}
            self.last_seq = seq

            speed = max(0, min(255, int(cmd.get("speed", 0))))
            ms = max(0, min(500, int(cmd.get("duration_ms", 0))))
            if action == "forward":
                if self.distance_cm < REFLEX_STOP_CM:
                    self.last_event = "Obstacle Avoided"
                    return {"ok": False, "seq": seq, "refused": "obstacle_too_close"}
                self.distance_cm = max(5.0, self.distance_cm - speed * ms / 1000 * 0.25)
            elif action == "reverse":
                self.distance_cm += speed * ms / 1000 * 0.2
            elif action in ("turn_left", "turn_right"):
                self.distance_cm = self.rng.uniform(30, 220)
                self.clear_side = self.rng.choice(("left", "right"))
            self.moves += action != "stop"
            self.last_action = action
            return {"ok": True, "seq": seq, "executed": action}

    def set_mode(self, mode: str) -> None:
        with self.lock:
            self.mode = mode
            self.last_seq = None  # rover forgets the last seq when Jev Auto is switched on


def fake_jpeg(scene: dict[str, Any]) -> bytes:
    """A tiny JPEG-shaped blob carrying the scene in a COM (FFFE) segment."""
    payload = b"SIMSCENE:" + json.dumps(scene).encode() + b"\x00"
    return b"\xff\xd8" + b"\xff\xfe" + struct.pack(">H", len(payload) + 2) + payload + b"\xff\xd9"


def _handler(world: World, token: str, role: str, verbose: bool):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # noqa: D401 - keep the console quiet
            if verbose:
                super().log_message(fmt, *args)

        def _json(self, code: int, body: dict[str, Any]) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            url = urlparse(self.path)
            if url.path == "/id":
                self._json(200, {"board": role, "firmware": "sim"})
            elif role == "camera" and url.path == "/capture":
                data = fake_jpeg(world.scene())
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif role == "rover" and url.path == "/sensors/data":
                self._json(200, world.telemetry())
            elif role == "rover" and url.path == "/mode":
                mode = parse_qs(url.query).get("set", [""])[0]
                if mode not in ("jev", "manual"):
                    self._json(400, {"error": "use /mode?set=jev or /mode?set=manual"})
                else:
                    world.set_mode(mode)
                    self._json(200, {"mode": mode})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if role != "rover" or urlparse(self.path).path != "/jev/cmd":
                self._json(404, {"error": "not found"})
                return
            if self.headers.get("X-Token") != token:
                self._json(401, {"ok": False, "refused": "bad_token"})
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                cmd = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._json(400, {"ok": False, "refused": "bad_json"})
                return
            self._json(200, world.command(cmd))

    return Handler


def start(
    world: World,
    token: str = "sim-token",
    host: str = "127.0.0.1",
    rover_port: int = 8081,
    camera_port: int = 8082,
    verbose: bool = False,
) -> tuple[ThreadingHTTPServer, ThreadingHTTPServer]:
    """Start both fake boards in background threads. Port 0 picks a free port."""
    servers = (
        ThreadingHTTPServer((host, rover_port), _handler(world, token, "rover", verbose)),
        ThreadingHTTPServer((host, camera_port), _handler(world, token, "camera", verbose)),
    )
    for srv in servers:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    return servers


def main() -> None:
    p = argparse.ArgumentParser(description="Fake rover + camera for the Earth Station")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--rover-port", type=int, default=8081)
    p.add_argument("--camera-port", type=int, default=8082)
    p.add_argument("--token", default="sim-token", help="must match ROVER_CMD_TOKEN")
    p.add_argument("--mode", choices=("jev", "manual"), default="jev")
    p.add_argument("--verbose", action="store_true")
    a = p.parse_args()

    world = World(mode=a.mode)
    rover, camera = start(world, a.token, a.host, a.rover_port, a.camera_port, a.verbose)
    print(f"fake rover   http://{a.host}:{rover.server_address[1]}  (mode {a.mode})")
    print(f"fake camera  http://{a.host}:{camera.server_address[1]}")
    print(f"switch mode: http://{a.host}:{rover.server_address[1]}/mode?set=manual")
    print("Ctrl+C to stop")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        for srv in (rover, camera):
            srv.shutdown()


if __name__ == "__main__":
    main()
