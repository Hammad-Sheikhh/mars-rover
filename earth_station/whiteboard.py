"""The shared notebook every worker reads and writes.

Workers never call each other. They post what they learned here, stamped with
the time, so the decision maker can tell when something is too old to trust.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

# How much a turn changes the view: a 500 ms turn swings the camera a long way
# without moving the rover, so it counts as several forward steps.
TURN_STEPS = 6


def now_ms() -> float:
    return time.monotonic() * 1000


@dataclass
class Whiteboard:
    telemetry: dict[str, Any] | None = None
    telemetry_at: float = 0.0
    scene: dict[str, Any] | None = None
    scene_at: float = 0.0
    photo: bytes | None = None  # latest camera JPEG, for mission control
    photo_count: int = 0
    last_command: dict[str, Any] | None = None
    seq: int = 0
    # How much the view may have changed since the description was taken, and
    # the distance the rover saw at that moment. vision_policy.py reads these.
    moves_since_scene: int = 0
    scene_distance_cm: float | None = None
    unsure_at: float = 0.0
    stats: dict[str, int] = field(
        default_factory=lambda: {"decisions": 0, "sent": 0, "stopped_by_gate": 0, "refused": 0}
    )

    def post_telemetry(self, data: dict[str, Any]) -> None:
        self.telemetry, self.telemetry_at = data, now_ms()

    def post_scene(self, data: dict[str, Any]) -> None:
        self.scene, self.scene_at = data, now_ms()
        self.moves_since_scene = 0
        self.unsure_at = 0.0
        dist = (self.telemetry or {}).get("distance_cm")
        self.scene_distance_cm = float(dist) if isinstance(dist, (int, float)) else None

    def note_move(self, action: str) -> None:
        """Count a drive step the rover accepted, to know when the photo is old."""
        if action in ("forward", "reverse"):
            self.moves_since_scene += 1
        elif action in ("turn_left", "turn_right"):
            self.moves_since_scene += TURN_STEPS

    def note_unsure(self) -> None:
        self.unsure_at = now_ms()

    def post_photo(self, jpeg: bytes) -> None:
        self.photo, self.photo_count = jpeg, self.photo_count + 1

    def telemetry_age_ms(self) -> float | None:
        return None if self.telemetry is None else now_ms() - self.telemetry_at

    def scene_age_ms(self) -> float | None:
        return None if self.scene is None else now_ms() - self.scene_at

    @property
    def mode(self) -> str:
        """Rover drive mode as the rover reports it. Firmware without Jev support
        sends no 'mode', which counts as manual, so the station never drives it."""
        if not self.telemetry:
            return "unknown"
        return str(self.telemetry.get("mode", "manual")).lower()

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq
