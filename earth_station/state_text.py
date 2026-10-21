"""Numbers -> plain words for Jev.

Jev is weak at arithmetic, so all comparisons happen here in code and Jev only
reads the conclusions ("62 cm, clear" rather than just "62").
"""

from __future__ import annotations

from .config import Settings
from .whiteboard import Whiteboard

TILT_DANGER_DEG = 35
TILT_WARN_DEG = 15
ROUGH_VIBRATION = 0.08


def describe_distance(cm: float | None, safe_cm: int) -> str:
    if cm is None or cm < 0:
        return "unknown (no ultrasonic reading)"
    if cm < safe_cm / 2:
        return f"{cm:.0f} cm, very close, danger"
    if cm < safe_cm:
        return f"{cm:.0f} cm, close (under the {safe_cm} cm safe distance)"
    return f"{cm:.0f} cm, clear (safe distance is {safe_cm} cm)"


def orientation_word(pitch: float | None, roll: float | None) -> str:
    if pitch is None or roll is None:
        return "unknown"
    worst = max(abs(pitch), abs(roll))
    if worst > TILT_DANGER_DEG:
        return "dangerous tilt"
    return "tilted" if worst > TILT_WARN_DEG else "level"


def describe_orientation(pitch: float | None, roll: float | None) -> str:
    if pitch is None or roll is None:
        return "unknown"
    return f"{orientation_word(pitch, roll)} (pitch {pitch:.0f} deg, roll {roll:.0f} deg)"


def describe_terrain(vibration: float | None) -> str:
    if vibration is None:
        return "unknown"
    return "rough" if vibration > ROUGH_VIBRATION else "smooth"


def build(board: Whiteboard, settings: Settings) -> str:
    t = board.telemetry or {}
    lines = [
        f"Goal: {settings.goal}.",
        f"Distance ahead: {describe_distance(t.get('distance_cm'), settings.safe_distance_cm)}.",
        f"Orientation: {describe_orientation(t.get('pitch'), t.get('roll'))}.",
        f"Terrain: {describe_terrain(t.get('vibration'))}.",
    ]
    event = t.get("last_event")
    if event and event != "Nominal":
        # The firmware keeps an event for 8 s. A single wheel bump spikes the
        # accelerometer, stamps "Tilt Warning", and the rover is level again
        # 0.2 s later - but Jev then read a tilt hazard on ~96% of the
        # decisions of the 22 Oct run (164 of 171 briefs) and hedged to
        # forward 0.50 / stop 0.33. Only tell Jev about a tilt that is real now.
        if event == "Tilt Warning" and orientation_word(t.get("pitch"), t.get("roll")) == "level":
            lines.append(
                "Recent event: a bump spiked the tilt sensor while driving; "
                "the rover is level again now."
            )
        else:
            lines.append(f"Recent event: {event}.")

    if board.scene:
        age = board.scene_age_ms() or 0
        lines.append(f"Camera, {age / 1000:.1f} s ago: {board.scene['summary']}")
        side = board.scene.get("clear_side")
        if side == "none":
            lines.append("Open side: none (neither side is known to be open).")
        elif side in ("left", "right", "both"):
            lines.append(f"Open side: {side}.")
        blocked = board.scene.get("obstacle_ahead")
        if isinstance(blocked, bool):
            lines.append(f"Obstacle ahead: {'yes' if blocked else 'no'}.")
        if board.scene.get("hazards"):
            lines.append("Hazards: " + ", ".join(board.scene["hazards"]) + ".")
    else:
        lines.append("Camera: no description yet.")

    if board.last_command:
        c = board.last_command
        lines.append(f"Previous move: {c['action']} for {c['duration_ms']} ms.")
    return "\n".join(lines)
