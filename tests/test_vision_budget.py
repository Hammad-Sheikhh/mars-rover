"""Vision cost control: one description serves many decisions.

The rules are tested twice: as pure policy functions, and as a station against
the simulator with a fake vision AI (so no key, quota or internet is needed).
"""

import asyncio
import time
from dataclasses import replace

import httpx

from earth_station import sim, vision_policy
from earth_station.describe import DescribeError
from earth_station.logger import Logger
from earth_station.station import Station
from earth_station.whiteboard import Whiteboard

SCENE = {
    "summary": "Open floor ahead.",
    "obstacle_ahead": False,
    "clear_side": "both",
    "hazards": [],
}


def board_with_scene(distance=120):
    b = Whiteboard()
    b.post_telemetry({"distance_cm": distance, "mode": "jev"})
    b.post_scene(dict(SCENE))
    return b


# ---------- the rules on their own ----------


def test_first_view_is_always_described(settings):
    assert vision_policy.refresh_reason(Whiteboard(), settings, None) == "no description yet"


def test_a_fresh_description_is_reused(settings):
    b = board_with_scene()
    assert vision_policy.refresh_reason(b, settings, 0.9) is None
    assert vision_policy.stale_reason(b, settings) is None


def test_enough_moves_ask_for_a_new_photo(settings):
    b = board_with_scene()
    for _ in range(settings.vision_refresh_moves - 1):
        b.note_move("forward")
    assert vision_policy.refresh_reason(b, settings, 0.9) is None

    b.note_move("forward")
    reason = vision_policy.refresh_reason(b, settings, 0.9)
    assert reason is not None and "moved" in reason


def test_two_turns_count_as_a_view_change(settings):
    b = board_with_scene()
    b.note_move("turn_left")
    assert vision_policy.refresh_reason(b, settings, 0.9) is None

    b.note_move("turn_right")
    # TURN_STEPS is 6, so two turns plus two forward steps reach the default 14.
    b.note_move("forward")
    assert vision_policy.refresh_reason(b, settings, 0.9) is None
    b.note_move("forward")
    assert vision_policy.refresh_reason(b, settings, 0.9) is not None


def test_an_aging_description_is_refreshed(settings):
    b = board_with_scene()
    b.scene_at -= settings.vision_refresh_ms + 100
    reason = vision_policy.refresh_reason(b, settings, 0.9)
    assert reason is not None and "old" in reason


def test_getting_close_asks_for_a_new_photo(settings):
    b = board_with_scene(distance=120)
    b.post_telemetry({"distance_cm": 55, "mode": "jev"})  # 65 cm closer than the photo
    reason = vision_policy.refresh_reason(b, settings, 0.9)
    assert reason is not None and "55 cm" in reason


def test_an_unsure_jev_refreshes_an_older_description(settings):
    b = board_with_scene()
    b.scene_at -= settings.vision_refresh_ms / 2 + 100
    b.note_unsure()
    reason = vision_policy.refresh_reason(b, settings, 0.40)
    assert reason == "Jev was unsure (0.40 on its last decision)"


def test_an_unsure_jev_does_not_refresh_a_fresh_description(settings):
    b = board_with_scene()
    b.note_unsure()
    assert vision_policy.refresh_reason(b, settings, 0.40) is None


def test_the_forward_view_goes_stale_after_too_many_moves(settings):
    b = board_with_scene()
    for _ in range(settings.scene_max_moves + 1):
        b.note_move("forward")
    assert vision_policy.stale_reason(b, settings) == "camera view is out of date"


def test_the_forward_view_goes_stale_on_the_clock(settings):
    b = board_with_scene()
    b.scene_at -= settings.scene_max_age_ms + 100
    assert vision_policy.stale_reason(b, settings) == "camera description too old"


# ---------- the station with a fake vision AI ----------


def station_settings(settings, rover, camera, **overrides):
    return replace(
        settings,
        rover_url=f"http://127.0.0.1:{rover.server_address[1]}",
        camera_url=f"http://127.0.0.1:{camera.server_address[1]}",
        describe_mode="live",
        vision_api_key="fake-key",
        camera_every_ms=5,
        decide_every_ms=1,
        telemetry_every_ms=5,
        **overrides,
    )


def test_a_long_run_uses_no_more_than_the_vision_budget(settings, monkeypatch):
    world = sim.World(mode="jev", seed=1)
    rover, camera = sim.start(world, token="sim-token", rover_port=0, camera_port=0)
    calls = []

    async def fake_describe(jpeg, s):
        calls.append(1)
        return world.scene()

    monkeypatch.setattr("earth_station.station.describe", fake_describe)
    s = station_settings(
        settings,
        rover,
        camera,
        vision_max_calls=6,
        vision_refresh_ms=10_000,
        vision_refresh_moves=1,  # every accepted move wants a photo: hit the cap
    )

    async def go():
        log = Logger(s.log_dir)
        async with httpx.AsyncClient() as client:
            st = Station(s, client, log)
            assert await st.preflight()  # one description, counted
            watcher = asyncio.create_task(st.camera_watcher())
            try:
                for _ in range(200):
                    st.board.post_telemetry(await st.rover.read())
                    await st.decide_once()
                    await asyncio.sleep(0)
            finally:
                watcher.cancel()
            await st.land()
        log.close()
        return st

    try:
        st = asyncio.run(go())
    finally:
        for srv in (rover, camera):
            srv.shutdown()

    assert st.board.stats["decisions"] == 200
    assert st.vision_calls == 6
    assert len(calls) == 6  # pre-flight plus five during the run, never more


def test_a_stationary_run_does_not_describe_again(settings, monkeypatch):
    world = sim.World(mode="jev", seed=1)
    rover, camera = sim.start(world, token="sim-token", rover_port=0, camera_port=0)
    calls = []

    async def fake_describe(jpeg, s):
        calls.append(1)
        return world.scene()

    monkeypatch.setattr("earth_station.station.describe", fake_describe)
    s = station_settings(settings, rover, camera, suggest_only=True)

    async def go():
        log = Logger(s.log_dir)
        async with httpx.AsyncClient() as client:
            st = Station(s, client, log)
            assert await st.preflight()
            watcher = asyncio.create_task(st.camera_watcher())
            await asyncio.sleep(0.3)  # many captures, no movement
            watcher.cancel()
            await st.land()
        log.close()
        return st

    try:
        st = asyncio.run(go())
    finally:
        for srv in (rover, camera):
            srv.shutdown()

    assert st.vision_calls == 1  # only the pre-flight description
    assert len(calls) == 1


def test_run_ends_cleanly_when_no_description_can_be_had(settings, monkeypatch):
    world = sim.World(mode="jev", seed=1)
    rover, camera = sim.start(world, token="sim-token", rover_port=0, camera_port=0)
    attempts = 0

    async def fake_describe(jpeg, s):
        nonlocal attempts
        attempts += 1
        if attempts > 1:  # pre-flight works, then the free quota is gone
            raise DescribeError("vision AI rate limit reached; try a bigger CAMERA_EVERY_MS")
        return world.scene()

    monkeypatch.setattr("earth_station.station.describe", fake_describe)
    s = station_settings(
        settings,
        rover,
        camera,
        scene_max_age_ms=100,
        vision_refresh_ms=50,
        vision_lost_stop_s=0.2,
    )

    async def go():
        log = Logger(s.log_dir)
        async with httpx.AsyncClient() as client:
            st = Station(s, client, log)
            assert await st.preflight()
            started = time.monotonic()
            await asyncio.wait_for(st.run(), timeout=5)
            elapsed = time.monotonic() - started
            await st.land()
        log.close()
        return st, elapsed

    try:
        st, elapsed = asyncio.run(go())
    finally:
        for srv in (rover, camera):
            srv.shutdown()

    assert st.vision_gave_up
    assert elapsed < 5  # it stopped by itself instead of waiting forever
    assert attempts == 2  # pre-flight, then one rate-limited try
    assert world.last_action == "stop"


def test_run_waits_for_the_last_description_in_flight(settings, monkeypatch):
    """A spent budget must not end the run while its last describe is still running."""
    world = sim.World(mode="jev", seed=1)
    rover, camera = sim.start(world, token="sim-token", rover_port=0, camera_port=0)
    calls = 0
    release = asyncio.Event()

    async def fake_describe(jpeg, s):
        nonlocal calls
        calls += 1
        if calls == 2:
            await release.wait()
        return world.scene()

    monkeypatch.setattr("earth_station.station.describe", fake_describe)
    s = station_settings(
        settings,
        rover,
        camera,
        vision_max_calls=2,
        scene_max_age_ms=200,
        vision_refresh_ms=100,
        vision_lost_stop_s=60,
    )

    async def go():
        log = Logger(s.log_dir)
        async with httpx.AsyncClient() as client:
            st = Station(s, client, log)
            assert await st.preflight()  # call 1
            task = asyncio.create_task(st.run())
            await asyncio.sleep(0.35)  # call 2 is in flight and the scene is stale
            assert not task.done(), "the run ended while its last describe was in flight"
            release.set()
            await asyncio.wait_for(task, timeout=5)
            await st.land()
        log.close()
        return st

    try:
        st = asyncio.run(go())
    finally:
        for srv in (rover, camera):
            srv.shutdown()

    assert calls == 2
    assert st.vision_calls == 2
    assert st.vision_gave_up
    assert world.last_action == "stop"


def test_run_ends_cleanly_when_the_budget_is_used_up(settings, monkeypatch):
    world = sim.World(mode="jev", seed=1)
    rover, camera = sim.start(world, token="sim-token", rover_port=0, camera_port=0)

    async def fake_describe(jpeg, s):
        return world.scene()

    monkeypatch.setattr("earth_station.station.describe", fake_describe)
    s = station_settings(
        settings,
        rover,
        camera,
        vision_max_calls=1,  # pre-flight spends it
        scene_max_age_ms=100,
        vision_refresh_ms=50,
        vision_lost_stop_s=60,  # only the budget can end this run
    )

    async def go():
        log = Logger(s.log_dir)
        async with httpx.AsyncClient() as client:
            st = Station(s, client, log)
            assert await st.preflight()
            await asyncio.wait_for(st.run(), timeout=5)
            await st.land()
        log.close()
        return st

    try:
        st = asyncio.run(go())
    finally:
        for srv in (rover, camera):
            srv.shutdown()

    assert st.vision_calls == 1
    assert st.vision_budget_spent
    assert st.vision_gave_up
    assert world.last_action == "stop"
