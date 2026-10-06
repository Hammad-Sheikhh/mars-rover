"""The Jev spending guard: a run makes at most JEV_MAX_CALLS live calls.

Everything here uses a fake TypeSafe API, so no test ever spends credits.
"""

import asyncio
from dataclasses import replace

import httpx
import pytest

from earth_station import config
from earth_station.__main__ import build_parser, jev_override
from earth_station.jev_client import JevBudgetError, JevClient
from earth_station.logger import Logger
from earth_station.station import Station
from earth_station.whiteboard import Whiteboard
from tests.test_jev_client import DOCUMENTED_REPLY


def _live(settings, max_calls):
    return replace(settings, jev_mode="live", jev_api_key="test-key", jev_max_calls=max_calls)


def test_client_stops_calling_at_the_limit(settings):
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=DOCUMENTED_REPLY)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            jev = JevClient(client, _live(settings, 2))
            await jev.ask("Path clear.", Whiteboard())
            await jev.ask("Path clear.", Whiteboard())
            with pytest.raises(JevBudgetError):
                await jev.ask("Path clear.", Whiteboard())
            return jev

    jev = asyncio.run(go())
    assert len(sent) == 2  # the third question never left the laptop
    assert (jev.calls, jev.input_tokens, jev.output_tokens) == (2, 608, 36)
    assert jev.usage_line() == "Jev used 2 of 2 calls | 608 tokens in, 36 out"


def test_pretend_jev_is_never_counted(settings):
    async def go():
        async with httpx.AsyncClient() as client:
            jev = JevClient(client, replace(settings, jev_max_calls=1))
            for _ in range(5):
                await jev.ask("Path clear.", Whiteboard())
            return jev

    assert asyncio.run(go()).calls == 0


def test_limit_must_be_at_least_one(settings):
    with pytest.raises(config.ConfigError, match="JEV_MAX_CALLS"):
        config.validate(replace(settings, jev_max_calls=0))


def test_default_limit_is_small(settings):
    assert settings.jev_max_calls == 20


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["--sim"], {"jev_mode": "mock"}),  # practice runs are free
        (["--sim", "--check"], {"jev_mode": "mock"}),
        (["--sim", "--live-jev"], {"jev_mode": "live"}),
        ([], {}),  # real boards: JEV_MODE from .env decides
    ],
)
def test_sim_uses_the_pretend_jev_unless_asked(args, expected):
    assert jev_override(build_parser().parse_args(args)) == expected


def test_station_stops_the_rover_and_ends_the_run_at_the_limit(settings):
    """With a limit of 3: 3 Jev answers, then a stop to the rover, then the run ends."""
    jev_calls, commands = [], []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.typesafe.ai":
            jev_calls.append(request)
            return httpx.Response(200, json=DOCUMENTED_REPLY)
        if request.url.path == "/jev/cmd":
            commands.append(request.read())
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404)

    s = replace(
        _live(settings, 3),
        rover_url="http://rover.test",
        camera_url="http://cam.test",
        decide_every_ms=1,
    )

    async def go():
        log = Logger(s.log_dir)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            st = Station(s, client, log)

            async def fresh_board():  # keep the readings fresh, as the real workers do
                while True:
                    st.board.post_telemetry({"mode": "jev", "distance_cm": 100})
                    st.board.post_scene(
                        {
                            "summary": "open floor",
                            "obstacle_ahead": False,
                            "clear_side": "both",
                            "hazards": [],
                        }
                    )
                    await asyncio.sleep(0)

            feeder = asyncio.create_task(fresh_board())
            await asyncio.wait_for(st.decision_maker(), timeout=5)  # returns by itself
            feeder.cancel()
        log.close()
        return st

    st = asyncio.run(go())
    assert len(jev_calls) == 3
    assert st.jev_budget_spent
    assert b'"stop"' in commands[-1]  # the last command the rover got was a stop
