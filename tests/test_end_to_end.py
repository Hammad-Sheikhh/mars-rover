"""Full loop against the built-in simulator: no hardware, no network beyond localhost."""

import asyncio
from dataclasses import replace

import httpx

from earth_station import sim
from earth_station.logger import Logger
from earth_station.station import Station


def run_station(settings, world, cycles=12, suggest_only=False):
    rover, camera = sim.start(world, token="sim-token", rover_port=0, camera_port=0)
    s = replace(
        settings,
        rover_url=f"http://127.0.0.1:{rover.server_address[1]}",
        camera_url=f"http://127.0.0.1:{camera.server_address[1]}",
        suggest_only=suggest_only,
    )

    async def go():
        log = Logger(s.log_dir)
        async with httpx.AsyncClient() as client:
            st = Station(s, client, log)
            assert await st.preflight()
            for _ in range(cycles):
                st.board.post_telemetry(await st.rover.read())
                st.board.post_scene(sim.World.scene(world))
                await st.decide_once()
            await st.land()
        log.close()
        return st, log

    try:
        return asyncio.run(go())
    finally:
        for srv in (rover, camera):
            srv.shutdown()


def test_jev_drives_the_simulated_rover(settings):
    world = sim.World(mode="jev", seed=1)
    st, log = run_station(settings, world)
    assert st.board.stats["decisions"] == 12
    assert st.board.stats["sent"] == 12
    assert world.moves > 0
    assert log.path.exists() and log.path.read_text().count('"kind": "decision"') == 12


def test_suggest_only_never_moves_the_rover(settings):
    world = sim.World(mode="jev", seed=1)
    st, _ = run_station(settings, world, suggest_only=True)
    assert st.board.stats["decisions"] == 12
    assert st.board.stats["sent"] == 0
    assert world.moves == 0


def test_manual_mode_rover_is_left_alone(settings):
    world = sim.World(mode="manual", seed=1)
    st, _ = run_station(settings, world)
    assert world.moves == 0
    assert st.board.stats["sent"] == 0


def test_wrong_token_is_rejected(settings):
    world = sim.World(mode="jev", seed=1)
    rover, camera = sim.start(world, token="right", rover_port=0, camera_port=0)
    try:
        r = httpx.post(
            f"http://127.0.0.1:{rover.server_address[1]}/jev/cmd",
            json={"seq": 1, "action": "forward", "speed": 100, "duration_ms": 100},
            headers={"X-Token": "wrong"},
        )
        assert r.status_code == 401
        assert world.moves == 0
    finally:
        for srv in (rover, camera):
            srv.shutdown()
