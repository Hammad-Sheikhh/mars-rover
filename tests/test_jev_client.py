"""Live Jev client against a fake TypeSafe API (no key or internet needed).

The reply shapes are copied from https://docs.typesafe.ai/api.
"""

import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from earth_station.jev_client import JevClient, JevError
from earth_station.links import ACTIONS
from earth_station.whiteboard import Whiteboard

DOCUMENTED_REPLY = {
    "model": "jev-1.13.0",
    "answers": {
        "next_action": {
            "type": "choice",
            "choice": "turn_right",
            "probabilities": {
                "forward": 0.05,
                "turn_left": 0.03,
                "turn_right": 0.88,
                "reverse": 0.02,
                "stop": 0.02,
            },
            "confidence": 0.81,
        },
        "path_blocked": {"type": "noul", "noul": 0.93},
    },
    "usage": {"input_tokens": 304, "output_tokens": 18},
}


def _ask(settings, handler):
    live = replace(settings, jev_mode="live", jev_api_key="test-key")

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await JevClient(client, live).ask("Obstacle 30 cm ahead.", Whiteboard())

    return asyncio.run(go())


def test_request_matches_the_api_reference(settings):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=DOCUMENTED_REPLY)

    _ask(settings, handler)

    assert seen["url"] == "https://api.typesafe.ai/v1/systemone"
    assert seen["auth"] == "Bearer test-key"
    body = seen["body"]
    assert body["model"] == "jev-latest"
    assert body["state"] == "Obstacle 30 cm ahead."
    choice = body["questions"]["next_action"]
    assert choice["type"] == "choice"
    assert set(choice["criteria"]) == set(ACTIONS)  # options go in a criteria map
    assert body["questions"]["path_blocked"]["type"] == "noul"


def test_documented_reply_becomes_a_decision(settings):
    d = _ask(settings, lambda request: httpx.Response(200, json=DOCUMENTED_REPLY))
    assert d.action == "turn_right"
    assert d.confidence == pytest.approx(0.88)
    assert d.path_blocked == pytest.approx(0.93)


@pytest.mark.parametrize(
    ("status", "words"), [(401, "API key"), (429, "rate-limited"), (529, "busy"), (500, "500")]
)
def test_api_errors_raise_so_the_gate_stops(settings, status, words):
    with pytest.raises(JevError, match=words):
        _ask(settings, lambda request: httpx.Response(status))
