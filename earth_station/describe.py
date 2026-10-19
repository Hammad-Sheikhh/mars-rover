"""Photo -> short scene description, using a vision AI.

Jev cannot see images, so a vision AI turns each camera frame into the
small dict below. Keep `summary` to one or two sentences: Jev gets less accurate
when its input is long.

    {
      "summary": "Chair leg about 50 cm ahead, slightly left. Open floor to the right.",
      "obstacle_ahead": true,
      "clear_side": "right",          # "left" | "right" | "both" | "none"
      "hazards": ["cable on floor"]
    }

DESCRIBE_MODE=mock reads the simulator's hidden scene (no internet, no key).
DESCRIBE_MODE=live sends the photo to the vision AI named in VISION_PROVIDER:
"gemini" is the cheap default (a free key from https://aistudio.google.com) and
"anthropic" is Claude. Either way the key goes into .env as VISION_API_KEY.
VISION_FOCUS (comma-separated) names the objects the room test cares about:
the AI is told to bias its answer towards them.

Try it on saved photos first; it prints the time taken too:

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
import httpx2

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

# The same schema in Gemini's dialect (OpenAPI-style upper-case type names, no
# "additionalProperties" key), so both providers enforce the agreed answer shape.
GEMINI_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "obstacle_ahead": {"type": "BOOLEAN"},
        "clear_side": {"type": "STRING", "enum": list(CLEAR_SIDES)},
        "hazards": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["summary", "obstacle_ahead", "clear_side", "hazards"],
}

# Gemini's REST endpoint; the model name and :generateContent go after this.
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

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
_gemini_clients: dict[str, httpx2.AsyncClient] = {}


class DescribeError(Exception):
    pass


def _prompt(settings: Settings) -> str:
    """The agreed prompt, plus one focus line when VISION_FOCUS is set."""
    if not settings.vision_focus:
        return PROMPT
    return PROMPT + (
        "\nPay special attention to these important objects: "
        f"{settings.vision_focus}. Mention each one you can see in summary or hazards."
    )


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


def _gemini_client(settings: Settings) -> httpx2.AsyncClient:
    # One client per key, reused for every photo (keeps the connection open).
    if settings.vision_api_key not in _gemini_clients:
        _gemini_clients[settings.vision_api_key] = httpx2.AsyncClient(
            base_url=GEMINI_BASE_URL,
            timeout=settings.vision_timeout_s,
            headers={"x-goog-api-key": settings.vision_api_key},
        )
    return _gemini_clients[settings.vision_api_key]


def _gemini_error(response: Any) -> str:
    """Google's own error text, e.g. 'API key not valid', or a short fallback."""
    try:
        detail = str(response.json().get("error", {}).get("message", ""))
    except ValueError:
        detail = ""
    return detail or response.text[:120]


async def _describe_gemini(jpeg: bytes, settings: Settings, client: Any = None) -> dict[str, Any]:
    client = client or _gemini_client(settings)
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": base64.standard_b64encode(jpeg).decode("ascii"),
                        }
                    },
                    {"text": _prompt(settings)},
                ],
            }
        ],
        "generationConfig": {
            # The answer must be JSON in the agreed shape.
            "responseMimeType": "application/json",
            "responseSchema": GEMINI_SCHEMA,
            "maxOutputTokens": 2000,
            # No thinking: describe directly and cheaply; Jev does the reasoning.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    try:
        response = await client.post(f"/models/{settings.vision_model}:generateContent", json=body)
        response.raise_for_status()
    except httpx2.HTTPStatusError as e:
        status, detail = e.response.status_code, _gemini_error(e.response)
        if status in (401, 403) or (status == 400 and "api key" in detail.lower()):
            raise DescribeError("vision AI rejected VISION_API_KEY; check the key in .env") from e
        if status == 429:
            raise DescribeError("vision AI rate limit reached; try a bigger CAMERA_EVERY_MS") from e
        raise DescribeError(f"vision AI error {status}: {detail}") from e
    except httpx2.TimeoutException as e:
        raise DescribeError(
            "vision AI took too long to answer; try a higher VISION_TIMEOUT_S"
        ) from e
    except httpx2.HTTPError as e:
        raise DescribeError("cannot reach the vision AI; is the laptop online?") from e

    data = response.json()
    candidates = data.get("candidates") or []
    # No candidates or a SAFETY/RECITATION finish: this photo got no description.
    finish = candidates[0].get("finishReason", "STOP") if candidates else "SAFETY"
    if finish == "MAX_TOKENS":
        raise DescribeError("vision AI answer was cut off")
    if finish != "STOP":
        raise DescribeError("vision AI declined to describe this photo")
    text = "".join(
        part.get("text", "") for part in candidates[0].get("content", {}).get("parts", [])
    )
    try:
        return json.loads(text)
    except ValueError as e:
        raise DescribeError("vision AI did not answer in the agreed format") from e


async def _describe_live(jpeg: bytes, settings: Settings, client: Any = None) -> dict[str, Any]:
    if not jpeg.startswith(b"\xff\xd8"):
        raise DescribeError("the camera did not send a JPEG photo")
    if settings.vision_provider == "gemini":
        return await _describe_gemini(jpeg, settings, client)
    return await _describe_claude(jpeg, settings, client)


async def _describe_claude(jpeg: bytes, settings: Settings, client: Any = None) -> dict[str, Any]:
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
                        {"type": "text", "text": _prompt(settings)},
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
