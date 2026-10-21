"""Rules checked on the laptop before any move reaches the rover.

The rover has its own reflexes too (distance, tilt, watchdog), so these are the
first of two safety layers. When in doubt: stop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import vision_policy
from .config import Settings
from .jev_client import Decision
from .whiteboard import Whiteboard


@dataclass(frozen=True)
class GateResult:
    command: dict[str, Any] | None  # None means: send nothing at all
    approved: bool  # True only when Jev's own move is passed through
    reason: str


def check(decision: Decision | None, board: Whiteboard, s: Settings) -> GateResult:
    # 1. Only drive in Jev mode. The phone always wins.
    if board.mode != "jev":
        return GateResult(None, False, f"rover in {board.mode} mode")

    def stop(reason: str) -> GateResult:
        return GateResult(make_command(board, "stop", 0, 0), False, reason)

    # 2. No old data.
    t_age = board.telemetry_age_ms()
    if t_age is None or t_age > s.telemetry_max_age_ms:
        return stop("telemetry too old")

    # 6 (checked early). Errors mean stop.
    if decision is None:
        return stop("no answer from Jev")

    # 2b. Forward needs a description that still matches the view. Turning in
    # place or reversing does not: the rover is not driving into the unknown
    # ahead, and the firmware's tilt and distance vetoes still guard it. This is
    # what lets a drive keep working while the camera waits for a new photo.
    if decision.action == "forward":
        stale = vision_policy.stale_reason(board, s)
        if stale:
            return stop(stale)
        # 2c. Keep a real gap. The firmware only vetoes under 20 cm (its emergency
        # reflex); on 22 Oct the rover pushed into a stool twice with 18-36 cm on
        # the sensor. The station now refuses forward inside SAFE_DISTANCE_CM
        # (45 cm) and lets the unstick manoeuvre reverse and pivot instead.
        # A negative distance is the rover's code for "no echo within ~2 m",
        # which means the floor ahead is wide open, so that one is allowed.
        dist = _distance(board)
        if dist is not None and 0 <= dist < s.safe_distance_cm:
            return stop(f"only {dist:.0f} cm ahead (safe distance is {s.safe_distance_cm} cm)")

    # 3. Jev must be sure.
    if decision.confidence < s.min_confidence:
        # Backing away from something close is allowed even when Jev is not
        # sure: it only adds clearance, and its five-way answer often splits
        # reverse from stop (22 Oct: reverse 0.48 while 18 cm from a stool leg,
        # and the rover sat there until someone moved it by hand). Forward and
        # turning keep the full floor, so nothing drives toward a hazard here.
        dist = _distance(board)
        if decision.action == "reverse" and dist is not None and 0 <= dist < s.safe_distance_cm:
            command = make_command(board, decision.action, s.max_speed, s.move_ms)
            return GateResult(command, True, "reversing away from an obstacle")
        return stop(f"Jev unsure ({decision.confidence:.2f})")

    # 4. Don't drive into what Jev itself flagged.
    if (
        decision.action == "forward"
        and decision.path_blocked is not None
        and decision.path_blocked >= s.blocked_threshold
    ):
        return stop("Jev says path blocked but chose forward")

    if decision.action == "stop":
        return GateResult(make_command(board, "stop", 0, 0), True, "Jev chose stop")

    # 5. Gentle limits.
    command = make_command(board, decision.action, s.max_speed, s.move_ms)
    return GateResult(command, True, "approved")


def _distance(board: Whiteboard) -> float | None:
    """Ultrasonic distance in cm, or None when there is no usable reading."""
    dist = (board.telemetry or {}).get("distance_cm")
    if isinstance(dist, bool) or not isinstance(dist, (int, float)):
        return None
    return float(dist)


def make_command(board: Whiteboard, action: str, speed: int, duration_ms: int) -> dict[str, Any]:
    return {
        "seq": board.next_seq(),
        "action": action,
        "speed": speed,
        "duration_ms": duration_ms,
    }
