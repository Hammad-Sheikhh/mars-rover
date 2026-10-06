"""Mission control against the simulator: STOP, Resume, the state the page shows,
and that only this laptop's own page can press the buttons."""

import asyncio
from dataclasses import replace

import httpx

from earth_station import sim
from earth_station.logger import Logger
from earth_station.mission_control import HEADER, MissionControl
from earth_station.station import Station

PAGE = {HEADER: "1"}


def run_with_page(settings, world, body):
    """Start the simulator, a station and mission control, then run body(st, client, url)."""
    rover, camera = sim.start(world, token="sim-token", rover_port=0, camera_port=0)
    s = replace(
        settings,
        rover_url=f"http://127.0.0.1:{rover.server_address[1]}",
        camera_url=f"http://127.0.0.1:{camera.server_address[1]}",
        mission_control_port=0,
    )

    async def go():
        log = Logger(s.log_dir)
        async with httpx.AsyncClient() as client:
            st = Station(s, client, log)
            assert await st.preflight()
            mc = MissionControl(st, asyncio.get_running_loop(), s.mission_control_port)
            url = mc.start()
            try:
                return await body(st, client, url, mc)
            finally:
                mc.close()
                log.close()

    try:
        return asyncio.run(go())
    finally:
        for srv in (rover, camera):
            srv.shutdown()


async def tick(st, world, n=1):
    for _ in range(n):
        st.board.post_telemetry(await st.rover.read())
        st.board.post_scene(sim.World.scene(world))
        await st.decide_once()


def test_stop_stops_the_rover_and_pauses_jev(settings):
    world = sim.World(mode="jev", seed=1)

    async def body(st, client, url, mc):
        await tick(st, world, 3)
        assert world.moves > 0

        r = await client.post(f"{url}/stop", headers=PAGE)
        assert r.status_code == 200 and r.json() == {"paused": True}
        assert world.last_action == "stop"

        moves, sent = world.moves, st.board.stats["sent"]
        await tick(st, world, 5)  # even an answer already on its way is dropped
        assert world.moves == moves
        assert st.board.stats["sent"] == sent
        assert world.last_action == "stop"

    run_with_page(settings, world, body)


def test_resume_lets_jev_drive_again(settings):
    world = sim.World(mode="jev", seed=1)

    async def body(st, client, url, mc):
        await client.post(f"{url}/stop", headers=PAGE)
        r = await client.post(f"{url}/resume", headers=PAGE)
        assert r.json() == {"paused": False}
        moves = world.moves
        await tick(st, world, 3)
        assert world.moves > moves

    run_with_page(settings, world, body)


def test_decision_maker_waits_while_paused(settings):
    world = sim.World(mode="jev", seed=1)
    settings = replace(settings, decide_every_ms=10)

    async def body(st, client, url, mc):
        await client.post(f"{url}/stop", headers=PAGE)
        before = st.board.stats["decisions"]
        worker = asyncio.create_task(st.decision_maker())
        await asyncio.sleep(0.1)
        worker.cancel()
        assert st.board.stats["decisions"] == before

    run_with_page(settings, world, body)


def test_state_has_what_the_page_shows(settings):
    world = sim.World(mode="jev", seed=1)

    async def body(st, client, url, mc):
        await tick(st, world, 2)
        page = await client.get(url)
        assert page.status_code == 200 and "STOP" in page.text

        s = (await client.get(f"{url}/state")).json()
        assert s["mode"] == "jev" and s["paused"] is False
        assert "distance_cm" in s["telemetry"]
        assert s["scene"]["summary"]
        assert s["last"]["action"] in sim.ACTIONS and s["last"]["approved"] is True
        assert s["links"]["rover"]["state"] == "ok"
        assert s["links"]["camera"]["state"] == "ok"
        assert s["links"]["vision"]["state"] == "off"  # no paid photo descriptions
        assert s["stats"]["decisions"] == 2
        assert s["photo_id"] >= 1

        photo = await client.get(f"{url}/photo")
        assert photo.headers["content-type"] == "image/jpeg"
        assert photo.content.startswith(b"\xff\xd8")

    run_with_page(settings, world, body)


def test_other_websites_cannot_press_the_buttons(settings):
    world = sim.World(mode="jev", seed=1)

    async def body(st, client, url, mc):
        # A form or script on another site can't add our header...
        assert (await client.post(f"{url}/resume")).status_code == 403
        assert (await client.post(f"{url}/stop")).status_code == 403
        assert st.paused is False
        # ...and a site that renames itself to reach us (DNS rebinding) is turned away.
        evil = {"Host": "evil.example", **PAGE}
        assert (await client.post(f"{url}/stop", headers=evil)).status_code == 403
        assert (
            await client.get(f"{url}/state", headers={"Host": "evil.example"})
        ).status_code == 403
        assert st.paused is False

    run_with_page(settings, world, body)


def test_only_this_laptop_can_connect(settings):
    world = sim.World(mode="jev", seed=1)

    async def body(st, client, url, mc):
        assert mc._server.server_address[0] == "127.0.0.1"
        assert url.startswith("http://127.0.0.1:")

    run_with_page(settings, world, body)
