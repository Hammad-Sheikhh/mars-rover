"""Photo -> short scene description.  OWNER: camera / vision teammate.

Jev cannot see images, so a vision AI turns each camera frame into the small
dict below. Keep `summary` to one or two sentences: Jev gets less accurate
when its input is long.

    {
      "summary": "Chair leg about 50 cm ahead, slightly left. Open floor to the right.",
      "obstacle_ahead": true,
      "clear_side": "right",          # "left" | "right" | "both" | "none"
      "hazards": ["cable on floor"]
    }

To plug in a real vision model, implement `_describe_live` and set
DESCRIBE_MODE=live and VISION_API_KEY in .env. Test it on saved photos first:

    python -m earth_station.describe path/to/photo.jpg
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from .config import Settings

CLEAR_SIDES = ("left", "right", "both", "none")


class DescribeError(Exception):
    pass


async def describe(jpeg: bytes, settings: Settings) -> dict[str, Any]:
    if settings.describe_mode == "mock":
        scene = _describe_mock(jpeg)
    else:
        scene = await _describe_live(jpeg, settings)
    return validate_scene(scene)


def validate_scene(scene: Any) -> dict[str, Any]:
    """Check the agreed shape so a bad description never reaches Jev."""
    if not isinstance(scene, dict):
        raise DescribeError("description must be a dict")
    summary = scene.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise DescribeError("description needs a non-empty 'summary'")
    if len(summary) > 300:
        raise DescribeError("'summary' is too long (max 300 characters); keep it short for Jev")
    if not isinstance(scene.get("obstacle_ahead"), bool):
        raise DescribeError("'obstacle_ahead' must be true or false")
    if scene.get("clear_side") not in CLEAR_SIDES:
        raise DescribeError(f"'clear_side' must be one of {CLEAR_SIDES}")
    hazards = scene.get("hazards", [])
    if not isinstance(hazards, list) or not all(isinstance(h, str) for h in hazards):
        raise DescribeError("'hazards' must be a list of strings")
    return {
        "summary": summary.strip(),
        "obstacle_ahead": scene["obstacle_ahead"],
        "clear_side": scene["clear_side"],
        "hazards": hazards,
    }


def _describe_mock(jpeg: bytes) -> dict[str, Any]:
    # The simulator's camera hides its scene in a JPEG comment segment so the
    # whole loop can be tested offline. Real photos fall back to a neutral scene.
    marker = b"SIMSCENE:"
    start = jpeg.find(marker)
    if start != -1:
        end = jpeg.find(b"\x00", start)
        try:
            return json.loads(jpeg[start + len(marker) : end if end != -1 else None])
        except ValueError:
            pass
    return {
        "summary": "No vision model connected; scene unknown.",
        "obstacle_ahead": False,
        "clear_side": "both",
        "hazards": [],
    }


async def _describe_live(jpeg: bytes, settings: Settings) -> dict[str, Any]:
    raise NotImplementedError(
        "Live vision is not implemented yet. Implement _describe_live in "
        "earth_station/describe.py, or set DESCRIBE_MODE=mock."
    )


if __name__ == "__main__":  # python -m earth_station.describe photo.jpg
    from .config import load

    if len(sys.argv) != 2:
        sys.exit("usage: python -m earth_station.describe path/to/photo.jpg")
    with open(sys.argv[1], "rb") as f:
        print(json.dumps(asyncio.run(describe(f.read(), load())), indent=2))
