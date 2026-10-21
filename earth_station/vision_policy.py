"""When a new photo is worth a vision call.

A description costs money or free-tier quota, while a Jev call is cheap (and the
rover makes one every half second). So one description must serve many
decisions. The camera watcher asks the vision AI again only when the view has
really changed or the answer is getting unreliable:

* the rover drove (or turned) enough since the photo,
* the description is getting old (but not yet too old for the safety gate),
* something close has come closer,
* Jev said it was unsure on its last decision,
* there is no description at all.

The hard limits live in `safety_gate.py` (`SCENE_MAX_AGE_MS`,
`SCENE_MAX_MOVES`); these rules are the polite, early refreshes that keep the
gate from ever having to stop for an old picture.
"""

from __future__ import annotations

from .config import Settings
from .whiteboard import Whiteboard

# A description is refreshed when the ultrasonic distance has dropped this much
# since the photo was taken (the interesting case: a chair leg appearing close).
CLOSE_DROP_CM = 20.0


def refresh_reason(
    board: Whiteboard, settings: Settings, last_confidence: float | None
) -> str | None:
    """Why a fresh description is wanted now, or None to reuse the last one."""
    if board.scene is None:
        return "no description yet"

    if board.moves_since_scene >= settings.vision_refresh_moves:
        return (
            f"the rover moved {board.moves_since_scene} steps since the photo "
            f"(VISION_REFRESH_MOVES is {settings.vision_refresh_moves})"
        )

    dist = _distance(board)
    if (
        dist is not None
        and 0 <= dist < settings.vision_close_cm
        and board.scene_distance_cm is not None
        and board.scene_distance_cm - dist >= CLOSE_DROP_CM
    ):
        return (
            f"something is {dist:.0f} cm ahead, "
            f"{board.scene_distance_cm - dist:.0f} cm closer than in the photo"
        )

    age = board.scene_age_ms() or 0
    if age >= settings.vision_refresh_ms:
        return (
            f"the description is {age / 1000:.0f} s old "
            f"(VISION_REFRESH_MS is {settings.vision_refresh_ms / 1000:.0f} s)"
        )

    if (
        last_confidence is not None
        and last_confidence < settings.min_confidence
        and board.unsure_at > board.scene_at
        and age >= settings.vision_refresh_ms / 2
    ):
        return f"Jev was unsure ({last_confidence:.2f} on its last decision)"
    return None


def stale_reason(board: Whiteboard, settings: Settings) -> str | None:
    """Why the description is too old to drive *forward*, or None if it is usable.

    Turning and reversing stay allowed with an old description: the rover does
    not translate into the unknown, and the firmware's own tilt and distance
    vetoes still guard those moves. Forward is different: it needs vision.
    """
    age = board.scene_age_ms()
    if age is None or age > settings.scene_max_age_ms:
        return "camera description too old"
    if board.moves_since_scene > settings.scene_max_moves:
        return "camera view is out of date"
    return None


def _distance(board: Whiteboard) -> float | None:
    dist = (board.telemetry or {}).get("distance_cm")
    if isinstance(dist, bool) or not isinstance(dist, (int, float)):
        return None
    return float(dist)
