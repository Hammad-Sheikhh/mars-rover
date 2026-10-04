"""Rules checked on the laptop before any move reaches the rover.

The rover has its own reflexes too (distance, tilt, watchdog), so these are the
first of two safety layers. When in doubt: stop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    s_age = board.scene_age_ms()
    if s_age is None or s_age > s.scene_max_age_ms:
        return stop("camera description too old")

    # 6 (checked early). Errors mean stop.
    if decision is None:
        return stop("no answer from Jev")

    # 3. Jev must be sure.
    if decision.confidence < s.min_confidence:
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


def make_command(board: Whiteboard, action: str, speed: int, duration_ms: int) -> dict[str, Any]:
    return {
        "seq": board.next_seq(),
        "action": action,
        "speed": speed,
        "duration_ms": duration_ms,
    }
