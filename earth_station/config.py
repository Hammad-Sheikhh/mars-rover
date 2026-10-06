"""Settings, read from the repo-root .env file (git-ignored).

Every setting has a simulator-friendly default, so a fresh clone runs with no
.env at all. The board addresses default to empty, which means "find them"
(finder.py): that also finds a simulator running on this laptop.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent


class ConfigError(Exception):
    """A setting is missing or invalid. The message says which one."""


@dataclass(frozen=True)
class Settings:
    rover_url: str  # empty: find it (finder.py)
    camera_url: str
    rover_cmd_token: str

    jev_mode: str  # "mock" (offline rules) or "live" (real Jev API)
    jev_api_url: str
    jev_api_key: str
    jev_model: str
    jev_max_calls: int  # live calls allowed per run, so a forgotten window can't spend credits

    describe_mode: str  # "mock" or "live" (Claude vision)
    vision_api_key: str  # Anthropic API key
    vision_model: str
    vision_effort: str  # how hard Claude thinks: low is fastest and cheapest
    vision_timeout_s: float

    telemetry_every_ms: int
    camera_every_ms: int
    decide_every_ms: int

    min_confidence: float
    blocked_threshold: float
    max_speed: int
    move_ms: int
    safe_distance_cm: int
    telemetry_max_age_ms: int
    scene_max_age_ms: int

    goal: str
    suggest_only: bool
    log_dir: Path


def _str(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int) -> int:
    raw = _str(name, str(default))
    try:
        return int(raw)
    except ValueError as e:
        raise ConfigError(f"{name} must be a whole number, got {raw!r}") from e


def _float(name: str, default: float) -> float:
    raw = _str(name, str(default))
    try:
        return float(raw)
    except ValueError as e:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from e


def load(env_file: Path | None = None, **overrides) -> Settings:
    """Load settings from .env (if present) and the environment, then validate."""
    load_dotenv(env_file or REPO_ROOT / ".env")

    s = Settings(
        rover_url=_str("ROVER_URL", "").rstrip("/"),
        camera_url=_str("CAMERA_URL", "").rstrip("/"),
        rover_cmd_token=_str("ROVER_CMD_TOKEN", "sim-token"),
        jev_mode=_str("JEV_MODE", "mock").lower(),
        jev_api_url=_str("JEV_API_URL", "https://api.typesafe.ai/v1/systemone"),
        jev_api_key=_str("JEV_API_KEY", ""),
        jev_model=_str("JEV_MODEL", "jev-latest"),
        jev_max_calls=_int("JEV_MAX_CALLS", 20),
        describe_mode=_str("DESCRIBE_MODE", "mock").lower(),
        vision_api_key=_str("VISION_API_KEY", ""),
        vision_model=_str("VISION_MODEL", "claude-opus-5-5"),
        vision_effort=_str("VISION_EFFORT", "low").lower(),
        vision_timeout_s=_float("VISION_TIMEOUT_S", 10.0),
        telemetry_every_ms=_int("TELEMETRY_EVERY_MS", 200),
        camera_every_ms=_int("CAMERA_EVERY_MS", 1500),
        decide_every_ms=_int("DECIDE_EVERY_MS", 500),
        min_confidence=_float("MIN_CONFIDENCE", 0.60),
        blocked_threshold=_float("BLOCKED_THRESHOLD", 0.70),
        max_speed=_int("MAX_SPEED", 170),
        move_ms=_int("MOVE_MS", 300),
        safe_distance_cm=_int("SAFE_DISTANCE_CM", 40),
        telemetry_max_age_ms=_int("TELEMETRY_MAX_AGE_MS", 500),
        scene_max_age_ms=_int("SCENE_MAX_AGE_MS", 3000),
        goal=_str("GOAL", "explore the room safely"),
        suggest_only=False,
        log_dir=REPO_ROOT / "runs",
    )
    s = replace(s, **overrides)
    validate(s)
    return s


def validate(s: Settings) -> None:
    if s.jev_mode not in ("mock", "live"):
        raise ConfigError(f"JEV_MODE must be 'mock' or 'live', got {s.jev_mode!r}")
    if s.describe_mode not in ("mock", "live"):
        raise ConfigError(f"DESCRIBE_MODE must be 'mock' or 'live', got {s.describe_mode!r}")
    if s.jev_mode == "live" and not s.jev_api_key:
        raise ConfigError(
            "JEV_MODE=live needs JEV_API_KEY in .env (get one at https://console.typesafe.ai/keys)"
        )
    if s.jev_max_calls < 1:
        raise ConfigError("JEV_MAX_CALLS must be 1 or more (live Jev calls allowed per run)")
    if s.describe_mode == "live" and not s.vision_api_key:
        raise ConfigError(
            "DESCRIBE_MODE=live needs VISION_API_KEY in .env "
            "(an Anthropic API key from https://console.anthropic.com)"
        )
    if s.vision_effort not in ("low", "medium", "high", "xhigh", "max"):
        raise ConfigError("VISION_EFFORT must be low, medium, high, xhigh or max")
    if s.vision_timeout_s <= 0:
        raise ConfigError("VISION_TIMEOUT_S must be more than 0")
    if not s.rover_cmd_token:
        raise ConfigError("ROVER_CMD_TOKEN is empty; set the same value as in rover1/secrets.h")
    if not 0 < s.min_confidence <= 1:
        raise ConfigError("MIN_CONFIDENCE must be between 0 and 1")
    if not 0 < s.max_speed <= 255:
        raise ConfigError("MAX_SPEED must be between 1 and 255")
    if not 0 < s.move_ms <= 500:
        raise ConfigError("MOVE_MS must be between 1 and 500 (the rover caps moves at 500 ms)")
