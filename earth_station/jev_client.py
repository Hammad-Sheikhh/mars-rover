"""Ask Jev for the next move.

JEV_MODE=mock  - offline rule-based stand-in with the same output shape, so the
                 whole loop runs without an account or internet.
JEV_MODE=live  - calls the real Typesafe Jev API.

Request and reply follow TypeSafe's API reference (https://docs.typesafe.ai/api):
POST {state, model, questions} to /v1/systemone with a Bearer key. A choice
question lists its options as a `criteria` map (option -> what it means); the
reply gives `probabilities` per option. A noul reply is a 0-1 `noul` value.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings
from .links import ACTIONS
from .whiteboard import Whiteboard


class JevError(Exception):
    pass


@dataclass(frozen=True)
class Decision:
    action: str
    confidence: float
    probabilities: dict[str, float]
    path_blocked: float | None
    latency_ms: float


QUESTIONS: dict[str, Any] = {
    "next_action": {
        "type": "choice",
        "instructions": "The safest move that still makes progress toward the goal",
        "criteria": {
            "forward": "Drive straight ahead; only when the path ahead is clear",
            "turn_left": "Turn left on the spot, toward open space on the left",
            "turn_right": "Turn right on the spot, toward open space on the right",
            "reverse": "Back up; when something is very close ahead",
            "stop": "Stay still; when unsure, tilted, or nowhere is safe",
        },
    },
    "path_blocked": {
        "type": "noul",
        "instructions": "Something blocks the path straight ahead of the rover",
        "criteria": {
            "true": "An obstacle, wall or drop is close ahead",
            "false": "The path straight ahead is open",
        },
    },
}


class JevClient:
    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self._client = client
        self._s = settings

    async def ask(self, state: str, board: Whiteboard) -> Decision:
        start = time.perf_counter()
        if self._s.jev_mode == "mock":
            probs, blocked = _mock_policy(board, self._s.safe_distance_cm)
        else:
            answers = await self._call_api(state)
            probs = _parse_choice(answers.get("next_action"))
            blocked = _parse_noul(answers.get("path_blocked"))
        action = max(probs, key=probs.get)
        return Decision(
            action=action,
            confidence=probs[action],
            probabilities=probs,
            path_blocked=blocked,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    async def ping(self) -> float:
        """Small test call for pre-flight. Returns latency in ms."""
        board = Whiteboard()
        d = await self.ask("Pre-flight check. Rover is parked and not moving.", board)
        return d.latency_ms

    async def _call_api(self, state: str) -> dict[str, Any]:
        try:
            r = await self._client.post(
                self._s.jev_api_url,
                json={"state": state, "model": self._s.jev_model, "questions": QUESTIONS},
                headers={"Authorization": f"Bearer {self._s.jev_api_key}"},
                timeout=2.0,
            )
        except httpx.HTTPError as e:
            raise JevError(f"Jev API unreachable: {e}") from e
        if r.status_code in (401, 403):
            raise JevError("Jev rejected the API key (check JEV_API_KEY)")
        if r.status_code in (429, 529):
            raise JevError(
                f"Jev is busy or rate-limited (HTTP {r.status_code}); stopping this turn"
            )
        if r.status_code >= 400:
            raise JevError(f"Jev API returned HTTP {r.status_code}")
        try:
            answers = r.json()["answers"]
        except (ValueError, KeyError, TypeError) as e:
            raise JevError("Jev response has no 'answers' object") from e
        if not isinstance(answers, dict):
            raise JevError("Jev 'answers' is not an object")
        return answers


def _parse_choice(answer: Any) -> dict[str, float]:
    """Read option -> probability. The API puts it under 'probabilities' (and the
    winning option, a string, under 'choice'); older write-ups used other keys."""
    if not isinstance(answer, dict):
        raise JevError("missing 'next_action' answer")
    for key in ("probabilities", "choice", "distribution"):
        dist = answer.get(key)
        if isinstance(dist, dict):
            probs = {a: float(dist.get(a, 0.0)) for a in ACTIONS}
            if sum(probs.values()) <= 0:
                raise JevError("'next_action' probabilities are all zero")
            return probs
    raise JevError(f"unrecognised 'next_action' answer shape: {sorted(answer)}")


def _parse_noul(answer: Any) -> float | None:
    if not isinstance(answer, dict):
        return None
    value = answer.get("noul")
    return float(value) if isinstance(value, (int, float)) else None


def _mock_policy(board: Whiteboard, safe_cm: int) -> tuple[dict[str, float], float]:
    """Simple stand-in: go forward when clear, turn toward the clear side when not."""
    t = board.telemetry or {}
    scene = board.scene or {}
    dist = t.get("distance_cm")
    blocked = dist is not None and 0 <= dist < safe_cm
    if scene.get("obstacle_ahead"):
        blocked = True

    probs = dict.fromkeys(ACTIONS, 0.02)
    if dist is not None and 0 <= dist < safe_cm / 2:
        probs["reverse"] = 0.70
        probs["stop"] = 0.20
    elif blocked:
        side = scene.get("clear_side", "right")
        probs["turn_left" if side == "left" else "turn_right"] = 0.85
    else:
        probs["forward"] = 0.90
    total = sum(probs.values())
    return {a: p / total for a, p in probs.items()}, (0.9 if blocked else 0.1)
