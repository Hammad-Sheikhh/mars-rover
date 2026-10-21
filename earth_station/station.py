"""The Earth Station: four workers sharing one whiteboard.

sensor reader   every TELEMETRY_EVERY_MS   rover /sensors/data -> whiteboard
camera watcher  every CAMERA_EVERY_MS      camera /capture -> describe -> whiteboard
decision maker  every DECIDE_EVERY_MS      whiteboard -> words -> Jev -> gate -> rover
logger          always                     screen + runs/*.jsonl

Mission control (mission_control.py) reads snapshot() and calls pause()/resume().
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from collections import deque
from typing import Any

import httpx

from . import safety_gate, state_text, vision_policy
from .config import Settings
from .describe import DescribeError, describe
from .jev_client import Decision, JevBudgetError, JevClient, JevError
from .links import CameraLink, LinkError, RoverLink
from .logger import Logger, paint
from .whiteboard import Whiteboard

HISTORY = 20  # recent decisions shown on mission control
# Getting unstuck: when the rover's own 20 cm veto refuses a forward move it is
# nosed into something, and Jev tends to alternate forward and reverse there
# (22 Oct run: 18 cm from a stool leg, reverse at 0.48 = refused by the gate, so
# the rover sat still). The station backs off once, then pivots about 90 degrees
# so the camera sees a new way. Both moves are allowed with an old photo: they
# do not translate into the unknown.
ESCAPE_MS = 500
ESCAPE_SETTLE_MS = 250  # time for the wheels to stop and the distance reading to settle
ESCAPE_TURNS = 3
ESCAPE_GIVE_UP = 3  # manoeuvres in a row without room: stop and ask the human
VISION_BACKOFF_START_S = (
    15.0  # a 429 means "slow down": retrying every 5 s keeps the quota saturated
)
VISION_BACKOFF_MAX_S = 120.0


def _next_vision_backoff(current_s: float) -> float:
    """15 s after the first rate limit, then double, capped at 2 minutes."""
    return VISION_BACKOFF_START_S if current_s <= 0 else min(VISION_BACKOFF_MAX_S, current_s * 2)


def _distance(board: Whiteboard) -> float | None:
    """Ultrasonic distance in cm, or None when there is no usable reading (-1/no echo)."""
    dist = (board.telemetry or {}).get("distance_cm")
    if isinstance(dist, bool) or not isinstance(dist, (int, float)):
        return None
    return float(dist)


def _cm(value: float | None) -> str:
    return "no reading" if value is None else f"{value:.0f} cm"


def _forward_blocked_by_distance(gate: safety_gate.GateResult) -> bool:
    """True when the gate stopped a forward move because the gap is too small."""
    return bool(gate.command and gate.command["action"] == "stop" and "cm ahead" in gate.reason)


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
        self._hold_reason: str | None = None  # why we are not asking Jev right now
        self.last: dict[str, Any] | None = None  # Jev's last choice and what the gate did
        self.history: deque[dict[str, Any]] = deque(maxlen=HISTORY)  # newest last
        # Vision is the expensive part: count every live description attempt.
        self.vision_calls = 0
        self.vision_budget_spent = False  # the log line is printed once, not every cycle
        self.vision_gave_up = False  # ended the run because no description could be had
        self.last_vision_ok_at: float | None = None  # time.monotonic() of the last good one
        self.last_vision_reason: str | None = None  # why the last photo was described
        self.last_vision_error: str | None = None
        self.vision_in_flight = False  # the last allowed description may still arrive
        # Moves left in an unstick manoeuvre (reverse once, then pivot). Empty is normal.
        self._escape_phase: str | None = None  # None | "reverse" | "check" | "turns"
        self._escape_steps: list[str] = []
        self._escape_dist_before: float | None = None
        self._escapes_without_room = 0

    # ---------- pre-flight ----------
    async def _read_rover_with_retry(self, attempts: int = 3) -> dict[str, Any]:
        """The rover's /sensors/data hiccups for a fraction of a second every ~20 s.
        One bad read must not abort pre-flight, so give it a few quick tries."""
        last: LinkError | None = None
        for i in range(attempts):
            try:
                return await self.rover.read()
            except LinkError as e:
                last = e
                if i < attempts - 1:
                    await asyncio.sleep(0.5)
        assert last is not None
        raise last

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
            t = await self._read_rover_with_retry()
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
            scene = await self._describe_photo(photo, "pre-flight")
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

        if s.describe_mode == "live":
            log.check(
                True,
                f"vision: {self.vision_calls} of {s.vision_max_calls} descriptions used "
                "(pre-flight counts; the run reuses the rest)",
            )
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
        backoff_s = 0.0  # grows after a rate limit (429), reset on any good answer
        while True:
            try:
                # Capture is free; only describing costs money/quota. So the
                # photo stays fresh on mission control even when the description
                # is reused.
                photo = await self.camera.capture()
                self.board.post_photo(photo)
                self._clear_error("camera")

                why = vision_policy.refresh_reason(self.board, self.s, self._last_confidence())
                if why is None:
                    pass  # reuse the last description: no vision call at all
                elif not self._vision_has_budget():
                    if not self.vision_budget_spent:
                        self.vision_budget_spent = True
                        self.log.info(
                            f"vision: budget used up ({self.vision_calls} of "
                            f"{self.s.vision_max_calls} descriptions); reusing the last one",
                            "yellow",
                        )
                else:
                    scene = await self._describe_photo(photo, why)
                    self._clear_error("vision")
                    backoff_s = 0.0
                    if scene["summary"] != last_summary:
                        self.log.scene(scene)
                        last_summary = scene["summary"]
            except LinkError as e:
                self._error("camera", str(e))
            except DescribeError as e:
                self._error("vision", str(e))
                if "rate limit" in str(e).lower():
                    backoff_s = _next_vision_backoff(backoff_s)
                    self.log.info(
                        f"vision: rate limited; waiting {backoff_s:.0f} s for the quota to reset",
                        "yellow",
                    )
            # backoff_s is already in seconds; CAMERA_EVERY_MS is in milliseconds.
            await asyncio.sleep(backoff_s or self.s.camera_every_ms / 1000)

    def _vision_has_budget(self) -> bool:
        """Without live vision there is nothing to budget: the mock is free."""
        return self.s.describe_mode != "live" or self.vision_calls < self.s.vision_max_calls

    def _last_confidence(self) -> float | None:
        return None if self.last is None else self.last.get("confidence")

    async def _describe_photo(self, photo: bytes, why: str) -> dict[str, Any]:
        """One description. Every live attempt counts against VISION_MAX_CALLS:
        a request that times out or is rate-limited may still use quota."""
        live = self.s.describe_mode == "live"
        if live:
            if self.vision_calls >= self.s.vision_max_calls:
                raise DescribeError(
                    f"vision budget used up ({self.vision_calls} of "
                    f"{self.s.vision_max_calls} descriptions, VISION_MAX_CALLS in .env)"
                )
            self.vision_calls += 1
            self.last_vision_reason = why
            self.log.info(
                f"vision: describing because {why} "
                f"({self.vision_calls} of {self.s.vision_max_calls} this run)",
            )
        self.vision_in_flight = True
        try:
            scene = await describe(photo, self.s)
        except DescribeError as e:
            if live:
                self.last_vision_error = str(e)
            raise
        finally:
            self.vision_in_flight = False
        self.board.post_scene(scene)
        if live:
            self.last_vision_ok_at = time.monotonic()
            self.last_vision_error = None
        return scene

    async def decision_maker(self) -> None:
        """Returns when the Jev call limit is reached, which ends the run."""
        while not self.jev_budget_spent:
            if self.s.jev_mode == "live" and self.jev.calls >= self.s.jev_max_calls:
                # The last paid call is used up: end now, even if the scene is stale
                # (otherwise the freshness hold below would keep the run alive for nothing).
                self.log.info(
                    f"jev: Jev call limit reached ({self.jev.calls} calls, "
                    "JEV_MAX_CALLS in .env); stopping so no more credits are spent"
                )
                self.jev_budget_spent = True
                return
            if self.board.mode == "jev" and not self.paused:
                # Don't spend a paid call when the safety gate would veto the answer
                # anyway (old readings, or a photo description that hasn't arrived yet).
                wait = self._gate_wait_reason()
                if wait:
                    # Vision is different from a slow rover link: if no description
                    # can be had, waiting is forever. Stop the run cleanly instead.
                    give_up = self._vision_give_up_reason() if wait.startswith("camera") else None
                    if give_up:
                        self.vision_gave_up = True
                        self.log.info(f"vision: {give_up}", "red")
                        self.log.info(
                            "run ended: the rover was stopped, not left waiting", "yellow"
                        )
                        return
                    await self._hold(wait)
                else:
                    self._release_hold()
                    await self.decide_once()
            else:
                self._release_hold()
            await asyncio.sleep(self.s.decide_every_ms / 1000)

    def _gate_wait_reason(self) -> str | None:
        """Checked before asking Jev so credits aren't wasted on a vetoed answer."""
        t_age = self.board.telemetry_age_ms()
        if t_age is None or t_age > self.s.telemetry_max_age_ms:
            return "telemetry too old"
        return vision_policy.stale_reason(self.board, self.s)

    def _vision_give_up_reason(self) -> str | None:
        """Why no usable description can arrive any more, or None to keep waiting."""
        if self.s.describe_mode != "live":
            return None
        if self.vision_in_flight:
            # The last allowed description is still being written; giving up now
            # would waste it. If it fails, the budget check below ends the run.
            return None
        if self.vision_calls >= self.s.vision_max_calls:
            self.vision_budget_spent = True
            return (
                f"vision budget used up ({self.vision_calls} of "
                f"{self.s.vision_max_calls} descriptions, VISION_MAX_CALLS in .env) and the "
                "last description is too old; stopping so the rover does not drive blind"
            )
        if self.last_vision_ok_at is None:
            return None  # pre-flight always makes one, so there is a reference point
        lost_s = time.monotonic() - self.last_vision_ok_at
        if lost_s >= self.s.vision_lost_stop_s:
            return (
                f"no camera description for {lost_s:.0f} s "
                f"(VISION_LOST_STOP_S is {self.s.vision_lost_stop_s:.0f}); "
                "stopping so the rover does not drive blind"
            )
        return None

    async def _hold(self, reason: str) -> None:
        """Stop once, then wait quietly for fresh data instead of burning Jev calls."""
        if self._hold_reason == reason:
            return
        self._hold_reason = reason
        self.log.info(f"{reason}: holding, no Jev calls until fresh data arrives", "yellow")
        if not self.s.suggest_only:
            try:
                await self.rover.send(safety_gate.make_command(self.board, "stop", 0, 0))
            except LinkError as e:
                self._error("rover-cmd", str(e))

    def _release_hold(self) -> None:
        if self._hold_reason:
            self.log.info(f"{self._hold_reason} cleared: asking Jev again", "green")
            self._hold_reason = None

    async def decide_once(self) -> None:
        board, stats = self.board, self.board.stats
        state = state_text.build(board, self.s)
        escape_action: str | None = None
        if self._escape_phase is not None:
            escape_action = self._next_escape_step(board)
        if escape_action:
            # Unstick: no Jev call is spent on a move the station already knows.
            decision: Decision | None = Decision(
                escape_action, 0.95, {escape_action: 0.95}, None, 0.0
            )
            state = f"Recovery: {escape_action} to get clear of the obstacle.\n" + state
        else:
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
        if escape_action and gate.approved and gate.command:
            gate = dataclasses.replace(gate, command={**gate.command, "duration_ms": ESCAPE_MS})
        if decision is not None and decision.confidence < self.s.min_confidence:
            board.note_unsure()
        reply = None
        sent = None
        # Paused: STOP was pressed while Jev was answering, so this answer is dropped.
        if gate.command and not self.s.suggest_only and not self.paused:
            try:
                reply = await self.rover.send(gate.command)
                board.last_command = gate.command
                sent = gate.command["action"]
                stats["sent"] += 1
                if reply.get("ok"):
                    # A refused move did not change the view, so it is not counted.
                    board.note_move(sent)
                else:
                    stats["refused"] += 1
                    if reply.get("refused") == "obstacle_too_close" and self._escape_phase is None:
                        self._plan_escape(board)
            except LinkError as e:
                self._error("rover-cmd", str(e))
            # The gate may already refuse forward inside SAFE_DISTANCE_CM, in which
            # case the rover never gets the chance to refuse it: start the same
            # unstick manoeuvre instead of sitting there.
            if (
                self._escape_phase is None
                and not self.paused
                and decision is not None
                and decision.action == "forward"
                and _forward_blocked_by_distance(gate)
            ):
                self._plan_escape(board)
            if escape_action and sent:
                # Let the move finish before the next step: a new /jev/cmd replaces
                # the running move, so three turns sent 90 ms apart turned the
                # wheels for 270 ms in total, and the distance was measured
                # before the rover had moved at all (37 cm -> 37 cm at once).
                await asyncio.sleep((ESCAPE_MS + ESCAPE_SETTLE_MS) / 1000)
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
            "told_jev": state,
            "t": time.time(),
        }
        self.history.append(self.last)

    def _next_escape_step(self, board: Whiteboard) -> str | None:
        """The next unstick move, or None when the manoeuvre is over.

        Order: reverse once, then measure. If reversing won `ESCAPE_GAIN_CM` of
        room the rover is free again and Jev gets the next decision back. If the
        distance did not change (something low or thin that the wheels catch,
        or a wall behind), pivoting is the only way out, so turn `ESCAPE_TURNS`
        steps - about 90 degrees - and let the camera see somewhere new.
        """
        if self._escape_phase == "check":
            before = self._escape_dist_before
            after = _distance(board)
            if after is not None and after >= self.s.safe_distance_cm:
                # Enough room to drive on: hand the next decision back to Jev.
                self._escape_phase = None
                self._escapes_without_room = 0
                self.log.info(
                    f"recovery: reversing gained room ({_cm(before)} -> {_cm(after)}), "
                    "handing back to Jev",
                    "green",
                )
                return None
            side = (board.scene or {}).get("clear_side")
            turn = "turn_left" if side == "left" else "turn_right"
            self._escape_steps = [turn] * ESCAPE_TURNS
            self._escape_phase = "turns"
            self.log.info(
                f"recovery: reversing did not gain room "
                f"({_cm(before)} -> {_cm(after)}), pivoting {ESCAPE_TURNS} steps ({turn})",
                "yellow",
            )
            return self._next_escape_step(board)

        if self._escape_steps:
            action = self._escape_steps.pop(0)
            if not self._escape_steps:
                self._escape_phase = "check" if self._escape_phase == "reverse" else None
            return action
        self._escape_phase = None
        return None

    def _plan_escape(self, board: Whiteboard) -> None:
        """Not enough room ahead: back off once, then let the check decide."""
        if self._escapes_without_room >= ESCAPE_GIVE_UP:
            self._escape_steps = []
            self._escape_phase = None
            self.log.info(
                "recovery: no room in any direction after "
                f"{self._escapes_without_room} tries; stopping so the rover does not "
                "shuffle against the furniture (move it by hand or point it somewhere open)",
                "red",
            )
            return
        self._escapes_without_room += 1
        self._escape_phase = "reverse"
        self._escape_steps = ["reverse"]
        self._escape_dist_before = _distance(board)
        self.log.info(
            "recovery: not enough room ahead, so back off and measure the room",
            "yellow",
        )

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
            "history": list(self.history),
            "limits": {
                "min_confidence": self.s.min_confidence,
                "safe_distance_cm": self.s.safe_distance_cm,
            },
            "links": self._links(),
            "stats": dict(b.stats),
            "jev": {
                "mode": self.s.jev_mode,
                "calls": self.jev.calls,
                "max_calls": self.s.jev_max_calls,
                "budget_spent": self.jev_budget_spent,
            },
            "vision": {
                "mode": self.s.describe_mode,
                "calls": self.vision_calls,
                "max_calls": self.s.vision_max_calls,
                "budget_spent": self.vision_budget_spent,
                "gave_up": self.vision_gave_up,
                "last_reason": self.last_vision_reason,
                "last_error": self.last_vision_error,
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
            vision = link(
                "vision",
                b.scene is not None,
                f"{self.s.vision_model} | {self.vision_calls} of "
                f"{self.s.vision_max_calls} descriptions used",
            )
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
            # The decision maker finishes at the Jev call limit, or when vision
            # cannot produce a usable description any more.
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
        if self.s.describe_mode == "live":
            line = f"Vision used {self.vision_calls} of {self.s.vision_max_calls} descriptions"
            if self.last_vision_error:
                line += f" | last problem: {self.last_vision_error}"
            self.log.info(line, "yellow")

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
