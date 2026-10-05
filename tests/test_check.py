"""`--check`: every piece is tested and each problem comes with a fix."""

import asyncio
import socket
from dataclasses import replace

import pytest
from test_secrets import GOOD_ENV

from earth_station import check, secrets, sim


@pytest.fixture
def sim_settings(settings):
    world = sim.World(mode="jev", seed=1)
    rover, camera = sim.start(world, token="sim-token", rover_port=0, camera_port=0)
    yield replace(
        settings,
        rover_url=f"http://127.0.0.1:{rover.server_address[1]}",
        camera_url=f"http://127.0.0.1:{camera.server_address[1]}",
    )
    for srv in (rover, camera):
        srv.shutdown()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def links(s):
    return asyncio.run(check.run_checks(s, sim=True))


def test_everything_ok_against_the_simulator(sim_settings, capsys):
    results = links(sim_settings)
    assert all(r.ok for r in results), [r.what for r in results if not r.ok]
    assert check.report(results, sim=True) == 0
    assert "checks OK" in capsys.readouterr().out


def test_wrong_token_is_reported_with_a_fix(sim_settings):
    results = links(replace(sim_settings, rover_cmd_token="wrong-token"))
    bad = [r for r in results if not r.ok]
    assert len(bad) == 1
    assert "token" in bad[0].what and "earth_station.secrets" in bad[0].fix


def test_no_rover_says_where_to_look(sim_settings, capsys):
    results = links(replace(sim_settings, rover_url=f"http://127.0.0.1:{free_port()}"))
    bad = [r for r in results if not r.ok]
    assert len(bad) == 1
    assert "rover not found" in bad[0].what and "Serial monitor" in bad[0].fix
    assert check.report(results, sim=True) == 1
    assert "1 problem(s)" in capsys.readouterr().out


@pytest.fixture
def root(tmp_path):
    for board in secrets.BOARDS:
        (tmp_path / board).mkdir()
    (tmp_path / ".env").write_text(GOOD_ENV)
    return tmp_path


def test_board_files_match_after_the_helper(root, settings):
    secrets.make_secrets(root)
    token = secrets.read_defines(root / "rover1" / "secrets.h")["ROVER_CMD_TOKEN"]

    results = check.file_checks(replace(settings, rover_cmd_token=token), root)

    assert all(r.ok for r in results), [r.what for r in results if not r.ok]


def test_board_with_an_old_token_is_caught(root, settings):
    secrets.make_secrets(root)

    results = check.file_checks(replace(settings, rover_cmd_token="a-different-token"), root)

    bad = [r.what for r in results if not r.ok]
    assert bad == ["rover1/secrets.h doesn't match .env (ROVER_CMD_TOKEN)"]


def test_fresh_clone_lists_what_to_do(root, settings):
    (root / ".env").write_text("WIFI_SSID=\n")
    bad = [r for r in check.file_checks(settings, root) if not r.ok]
    whats = " ".join(r.what for r in bad)
    assert "WIFI_SSID" in whats and "rover token" in whats and "secrets.h is missing" in whats
    assert all(r.fix for r in bad)
