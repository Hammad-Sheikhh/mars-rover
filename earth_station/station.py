"""The Earth Station: four workers sharing one whiteboard.

sensor reader   every TELEMETRY_EVERY_MS   rover /sensors/data -> whiteboard
camera watcher  every CAMERA_EVERY_MS      camera /capture -> describe -> whiteboard
decision maker  every DECIDE_EVERY_MS      whiteboard -> words -> Jev -> gate -> rover
logger          always                     screen + runs/*.jsonl
"""

from __future__ import annotations

import asyncio

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
                scene = await describe(await self.camera.capture(), self.s)
                self.board.post_scene(scene)
                self._clear_error("camera")
                if scene["summary"] != last_summary:
                    self.log.scene(scene)
                    last_summary = scene["summary"]
            except (LinkError, DescribeError) as e:
                self._error("camera", str(e))
            await asyncio.sleep(self.s.camera_every_ms / 1000)

    async def decision_maker(self) -> None:
        """Returns when the Jev call limit is reached, which ends the run."""
        while not self.jev_budget_spent:
            if self.board.mode == "jev":
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
        if gate.command and not self.s.suggest_only:
            try:
                reply = await self.rover.send(gate.command)
                board.last_command = gate.command
                stats["sent"] += 1
                if not reply.get("ok"):
                    stats["refused"] += 1
            except LinkError as e:
                self._error("rover-cmd", str(e))
        stats["decisions"] += 1
        if gate.command and not gate.approved:
            stats["stopped_by_gate"] += 1
        self.log.decision(state, decision, gate, reply, self.s.suggest_only)

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
        if not self.s.suggest_only:
            try:
                await self.rover.send(safety_gate.make_command(self.board, "stop", 0, 0))
                print(paint("stop sent to rover", "yellow"))
            except (LinkError, ValueError):
                print(paint("could not send stop; the rover watchdog will stop it", "red"))
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

    # ---------- error throttling: print each distinct error once ----------
    def _error(self, source: str, message: str) -> None:
        if self._last_error.get(source) != message:
            self._last_error[source] = message
            self.log.info(f"{source}: {message}", "red")

    def _clear_error(self, source: str) -> None:
        if self._last_error.pop(source, None):
            self.log.info(f"{source}: recovered", "green")
