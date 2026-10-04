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


def describe_orientation(pitch: float | None, roll: float | None) -> str:
    if pitch is None or roll is None:
        return "unknown"
    worst = max(abs(pitch), abs(roll))
    word = (
        "dangerous tilt"
        if worst > TILT_DANGER_DEG
        else ("tilted" if worst > TILT_WARN_DEG else "level")
    )
    return f"{word} (pitch {pitch:.0f} deg, roll {roll:.0f} deg)"


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
        lines.append(f"Recent event: {event}.")

    if board.scene:
        age = board.scene_age_ms() or 0
        lines.append(f"Camera, {age / 1000:.1f} s ago: {board.scene['summary']}")
        if board.scene.get("hazards"):
            lines.append("Hazards: " + ", ".join(board.scene["hazards"]) + ".")
    else:
        lines.append("Camera: no description yet.")

    if board.last_command:
        c = board.last_command
        lines.append(f"Previous move: {c['action']} for {c['duration_ms']} ms.")
    return "\n".join(lines)
