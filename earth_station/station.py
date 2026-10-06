"""The Earth Station: four workers sharing one whiteboard.

sensor reader   every TELEMETRY_EVERY_MS   rover /sensors/data -> whiteboard
camera watcher  every CAMERA_EVERY_MS      camera /capture -> describe -> whiteboard
decision maker  every DECIDE_EVERY_MS      whiteboard -> words -> Jev -> gate -> rover
logger          always                     screen + runs/*.jsonl

Mission control (mission_control.py) reads snapshot() and calls pause()/resume().
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from . import safety_gate, state_text
from .config import Settings
from .describe import DescribeError, describe
from .jev_client import JevBudgetError, JevClient, JevError
from .links import CameraLink, LinkError, RoverLink
from .logger import Logger, paint
from .whiteboard import Whiteboard


class Station:
    def __init__(self, settings: Settings, client: httpx.AsyncClient, log: Logger):
        self.s = settings
        self.board = Whiteboard()
        self.rover = RoverLink(client, settings.rover_url, settings.rover_cmd_token)
        self.camera = CameraLink(client, settings.camera_url)
        self.jev = JevClient(client, settings)
        self.log = log
        self._last_error: dict[str, str] = {}
        self.jev_budget_spent = False
        self.paused = False  # STOP on mission control: no moves until Resume
        self.last: dict[str, Any] | None = None  # Jev's last choice and what the gate did

    # ---------- pre-flight ----------
    async def preflight(self) -> bool:
        s, log = self.s, self.log
        print(paint("Earth Station", "blue") + " pre-flight")
        log.check(True, f"rover {s.rover_url} | camera {s.camera_url}")
        log.check(
            True,
            f"Jev {s.jev_mode} | describe {s.describe_mode}"
            + (f" | at most {s.jev_max_calls} Jev calls" if s.jev_mode == "live" else "")
            + (" | SUGGEST ONLY" if s.suggest_only else ""),
        )
        ok = True

        try:
            t = await self.rover.read()
            self.board.post_telemetry(t)
            dist = t.get("distance_cm")
            log.check(True, f"rover answering | mode {self.board.mode} | distance {dist} cm")
            if "mode" not in t:
                log.check(
                    False,
                    "rover firmware has no Jev support yet ('mode' missing); "
                    "the station will watch but never drive",
                )
        except LinkError as e:
            ok = False
            log.check(False, f"{e}\n      check the rover is on and ROVER_URL is right")

        try:
            photo = await self.camera.capture()
            self.board.post_photo(photo)
            scene = await describe(photo, s)
            self.board.post_scene(scene)
            log.check(True, f'camera answering | {len(photo) / 1024:.1f} KB | "{scene["summary"]}"')
        except LinkError as e:
            ok = False
            log.check(False, f"{e}\n      check the camera is on and CAMERA_URL is right")
        except DescribeError as e:
            ok = False
            log.check(False, f"describe failed: {e}")

        try:
            ms = await self.jev.ping()
            log.check(True, f"Jev answering | {ms:.0f} ms")
        except JevError as e:
            ok = False
            log.check(False, str(e))

        log.check(True, f"logging to {log.path}")
        return ok

    # ---------- workers ----------
    async def sensor_reader(self) -> None:
        last_mode = self.board.mode
        while True:
            try:
                self.board.post_telemetry(await self.rover.read())
                self._clear_error("rover")
                if self.board.mode != last_mode:
                    self.log.mode(last_mode, self.board.mode)
                    last_mode = self.board.mode
            except LinkError as e:
                self._error("rover", str(e))
            await asyncio.sleep(self.s.telemetry_every_ms / 1000)

    async def camera_watcher(self) -> None:
        last_summary = self.board.scene["summary"] if self.board.scene else None
        while True:
            try:
                photo = await self.camera.capture()
                self.board.post_photo(photo)
                self._clear_error("camera")
                scene = await describe(photo, self.s)
                self.board.post_scene(scene)
                self._clear_error("vision")
                if scene["summary"] != last_summary:
                    self.log.scene(scene)
                    last_summary = scene["summary"]
            except LinkError as e:
                self._error("camera", str(e))
            except DescribeError as e:
                self._error("vision", str(e))
            await asyncio.sleep(self.s.camera_every_ms / 1000)

    async def decision_maker(self) -> None:
        """Returns when the Jev call limit is reached, which ends the run."""
        while not self.jev_budget_spent:
            if self.board.mode == "jev" and not self.paused:
                await self.decide_once()
            await asyncio.sleep(self.s.decide_every_ms / 1000)

    async def decide_once(self) -> None:
        board, stats = self.board, self.board.stats
        state = state_text.build(board, self.s)
        try:
            decision = await self.jev.ask(state, board)
            self._clear_error("jev")
        except JevBudgetError as e:
            self._error("jev", str(e))
            self.jev_budget_spent = True
            decision = None  # the gate turns this into a stop
        except JevError as e:
            self._error("jev", str(e))
            decision = None

        gate = safety_gate.check(decision, board, self.s)
        reply = None
        sent = None
        # Paused: STOP was pressed while Jev was answering, so this answer is dropped.
        if gate.command and not self.s.suggest_only and not self.paused:
            try:
                reply = await self.rover.send(gate.command)
                board.last_command = gate.command
                sent = gate.command["action"]
                stats["sent"] += 1
                if not reply.get("ok"):
                    stats["refused"] += 1
            except LinkError as e:
                self._error("rover-cmd", str(e))
        stats["decisions"] += 1
        if gate.command and not gate.approved:
            stats["stopped_by_gate"] += 1
        self.log.decision(state, decision, gate, reply, self.s.suggest_only)
        self.last = {
            "action": decision.action if decision else None,
            "confidence": decision.confidence if decision else None,
            "probabilities": decision.probabilities if decision else None,
            "approved": gate.approved,
            "reason": gate.reason,
            "sent": sent,
            "reply": reply,
            "t": time.time(),
        }

    # ---------- mission control ----------
    async def pause(self) -> None:
        """STOP button: stop the rover now and make no moves until resume()."""
        self.paused = True
        self.log.info("STOP pressed on mission control: rover stopped, Jev paused", "yellow")
        await self._send_stop()

    async def resume(self) -> None:
        self.paused = False
        self.log.info("Resume pressed on mission control: Jev may drive again", "green")

    async def snapshot(self) -> dict[str, Any]:
        """Everything the mission control page shows. Runs on the station's own loop."""
        b = self.board
        return {
            "mode": b.mode,
            "paused": self.paused,
            "suggest_only": self.s.suggest_only,
            "telemetry": b.telemetry,
            "telemetry_age_ms": _round(b.telemetry_age_ms()),
            "scene": b.scene,
            "scene_age_ms": _round(b.scene_age_ms()),
            "photo_id": b.photo_count,
            "last": self.last,
            "links": self._links(),
            "stats": dict(b.stats),
            "jev": {
                "mode": self.s.jev_mode,
                "calls": self.jev.calls,
                "max_calls": self.s.jev_max_calls,
                "budget_spent": self.jev_budget_spent,
            },
            "log": str(self.log.path),
        }

    def _links(self) -> dict[str, dict[str, str]]:
        def link(source: str, have_data: bool, ok: str) -> dict[str, str]:
            if source in self._last_error:
                return {"state": "error", "detail": self._last_error[source]}
            return {"state": "ok", "detail": ok} if have_data else {"state": "wait", "detail": ""}

        b = self.board
        rover = link("rover", b.telemetry is not None, self.s.rover_url)
        if rover["state"] == "ok" and "rover-cmd" in self._last_error:
            rover = {"state": "error", "detail": self._last_error["rover-cmd"]}
        if self.s.describe_mode == "mock":
            vision = {"state": "off", "detail": "off: Jev drives on the sensors only"}
        else:
            vision = link("vision", b.scene is not None, self.s.vision_model)
        if self.s.jev_mode == "mock":
            jev = {"state": "ok", "detail": "pretend Jev (free)"}
        else:
            jev = link("jev", True, f"{self.jev.calls} of {self.s.jev_max_calls} calls used")
        return {
            "rover": rover,
            "camera": link("camera", b.photo is not None, self.s.camera_url),
            "vision": vision,
            "jev": jev,
        }

    async def run(self) -> None:
        print(
            paint("waiting for Jev Auto (press it on the rover's AP page)", "yellow")
            if self.board.mode != "jev"
            else paint("rover already in Jev Auto", "yellow")
        )
        workers = [
            asyncio.create_task(w())
            for w in (self.sensor_reader, self.camera_watcher, self.decision_maker)
        ]
        try:
            # Only the decision maker ever finishes: when the Jev call limit is reached.
            await asyncio.wait(workers, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for w in workers:
                w.cancel()

    async def land(self) -> None:
        """Send a final stop and print a summary. Called on Ctrl+C or any crash."""
        await self._send_stop()
        st = self.board.stats
        print(
            paint(
                f"{st['decisions']} decisions | {st['sent']} sent | "
                f"{st['stopped_by_gate']} stopped by gate | {st['refused']} refused by rover | "
                f"log {self.log.path}",
                "dim",
            )
        )
        if self.s.jev_mode == "live":
            self.log.info(self.jev.usage_line(), "yellow")

    async def _send_stop(self) -> None:
        if self.s.suggest_only:
            return  # suggest-only never moves the rover, so there is nothing to stop
        try:
            await self.rover.send(safety_gate.make_command(self.board, "stop", 0, 0))
            print(paint("stop sent to rover", "yellow"))
        except (LinkError, ValueError):
            print(paint("could not send stop; the rover watchdog will stop it", "red"))

    # ---------- error throttling: print each distinct error once ----------
    def _error(self, source: str, message: str) -> None:
        if self._last_error.get(source) != message:
            self._last_error[source] = message
            self.log.info(f"{source}: {message}", "red")

    def _clear_error(self, source: str) -> None:
        if self._last_error.pop(source, None):
            self.log.info(f"{source}: recovered", "green")


def _round(ms: float | None) -> int | None:
    return None if ms is None else round(ms)
