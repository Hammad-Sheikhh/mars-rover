"""Photo -> short scene description, using Claude's vision.

Jev cannot see images, so a vision AI (Claude) turns each camera frame into the
small dict below. Keep `summary` to one or two sentences: Jev gets less accurate
when its input is long.

    {
      "summary": "Chair leg about 50 cm ahead, slightly left. Open floor to the right.",
      "obstacle_ahead": true,
      "clear_side": "right",          # "left" | "right" | "both" | "none"
      "hazards": ["cable on floor"]
    }

DESCRIBE_MODE=mock reads the simulator's hidden scene (no internet, no key).
DESCRIBE_MODE=live sends the photo to Claude: put an Anthropic API key in .env
as VISION_API_KEY. Try it on saved photos first; it prints the time taken too:

    python -m earth_station.describe path/to/photo.jpg [more.jpg ...]
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import time
from typing import Any

import anthropic

from .config import Settings

CLEAR_SIDES = ("left", "right", "both", "none")

# Models that accept the server-side refusal fallback: if one model wrongly
# declines a photo, another one answers, so a false alarm doesn't blind the rover.
FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5")

PROMPT = """You are the eyes of a small wheeled rover. This photo is from its \
front camera, about 10 cm above the floor. A driver who cannot see the photo \
decides the next move from your answer alone.

Reply with:
- summary: one or two short sentences (under 200 characters). Say what is \
directly ahead and roughly how far, then which way looks open.
- obstacle_ahead: true if something would block the rover within about 1 metre \
straight ahead.
- clear_side: where the rover could turn to find open floor: "left", "right", \
"both" or "none".
- hazards: short names of anything risky (stairs, drop, cable, liquid, pet, \
person's feet). Empty list if none.

If the photo is too dark or blurry to judge, say so in the summary, set \
obstacle_ahead to true and clear_side to "none"."""

SCENE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "obstacle_ahead": {"type": "boolean"},
        "clear_side": {"type": "string", "enum": list(CLEAR_SIDES)},
        "hazards": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "obstacle_ahead", "clear_side", "hazards"],
    "additionalProperties": False,
}

# What Jev reads for a real photo when nothing can look at it (DESCRIBE_MODE=mock).
# It must never claim the way is clear (SPEC D5). obstacle_ahead stays false so
# the distance sensor, not a guess, decides whether the rover may go forward.
NO_VISION = {
    "summary": "No camera vision (photo descriptions are off). "
    "Judge what is ahead from the distance sensor only.",
    "obstacle_ahead": False,
    "clear_side": "none",
    "hazards": [],
}

_clients: dict[str, anthropic.AsyncAnthropic] = {}


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
    # whole loop can be tested offline. Real photos get NO_VISION.
    marker = b"SIMSCENE:"
    start = jpeg.find(marker)
    if start != -1:
        end = jpeg.find(b"\x00", start)
        try:
            return json.loads(jpeg[start + len(marker) : end if end != -1 else None])
        except ValueError:
            pass
    return dict(NO_VISION)


def _client(settings: Settings) -> anthropic.AsyncAnthropic:
    # One client per key, reused for every photo (keeps the connection open).
    if settings.vision_api_key not in _clients:
        _clients[settings.vision_api_key] = anthropic.AsyncAnthropic(
            api_key=settings.vision_api_key,
            timeout=settings.vision_timeout_s,
            max_retries=1,
        )
    return _clients[settings.vision_api_key]


async def _describe_live(jpeg: bytes, settings: Settings, client: Any = None) -> dict[str, Any]:
    if not jpeg.startswith(b"\xff\xd8"):
        raise DescribeError("the camera did not send a JPEG photo")
    client = client or _client(settings)
    extra: dict[str, Any] = {}
    if settings.vision_model in FALLBACK_MODELS:
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    image = base64.standard_b64encode(jpeg).decode("ascii")
    try:
        response = await client.beta.messages.create(
            model=settings.vision_model,
            max_tokens=2000,
            output_config={
                "effort": settings.vision_effort,
                "format": {"type": "json_schema", "schema": SCENE_SCHEMA},
            },
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": image},
                        },
                        {"type": "text", "text": PROMPT},
                    ],
                }
            ],
            **extra,
        )
    except anthropic.AuthenticationError as e:
        raise DescribeError("vision AI rejected VISION_API_KEY; check the key in .env") from e
    except anthropic.RateLimitError as e:
        raise DescribeError("vision AI rate limit reached; try a bigger CAMERA_EVERY_MS") from e
    except anthropic.APIStatusError as e:
        raise DescribeError(f"vision AI error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise DescribeError("cannot reach the vision AI; is the laptop online?") from e

    if response.stop_reason == "refusal":
        raise DescribeError("vision AI declined to describe this photo")
    if response.stop_reason == "max_tokens":
        raise DescribeError("vision AI answer was cut off")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except ValueError as e:
        raise DescribeError("vision AI did not answer in the agreed format") from e


async def _try_photos(paths: list[str]) -> None:
    from .config import load

    settings = load()
    print(f"describe {settings.describe_mode}, model {settings.vision_model}")
    for path in paths:
        with open(path, "rb") as f:
            jpeg = f.read()
        start = time.perf_counter()
        try:
            scene = await describe(jpeg, settings)
        except DescribeError as e:
            print(f"\n{path}: FAILED: {e}")
            continue
        print(f"\n{path} ({time.perf_counter() - start:.1f} s)")
        print(json.dumps(scene, indent=2))


if __name__ == "__main__":  # python -m earth_station.describe photo.jpg [more.jpg ...]
    if len(sys.argv) < 2:
        sys.exit("usage: python -m earth_station.describe path/to/photo.jpg [more.jpg ...]")
    asyncio.run(_try_photos(sys.argv[1:]))
