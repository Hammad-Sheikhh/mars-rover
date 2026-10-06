"""Run the Earth Station.

python -m earth_station              # find the boards on the hotspot and drive
python -m earth_station --sim        # start the built-in simulator and use it (pretend Jev)
python -m earth_station --sim --live-jev   # simulator + the real Jev (spends credits)
python -m earth_station --suggest    # decide and log, but never send moves
python -m earth_station --check      # test every piece and say how to fix it (add --sim to try)

Each run opens mission control in your browser (http://127.0.0.1:8000), with a STOP button.
Add --no-browser to skip opening it; the address is printed either way.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import webbrowser

import httpx

from . import check, config, finder, sim
from .logger import Logger, paint
from .mission_control import MissionControl
from .station import Station


async def _find(settings: config.Settings, client: httpx.AsyncClient) -> config.Settings | None:
    """Fill in the board addresses. None if a board can't be found (the fix is printed)."""
    print(paint("Finding the boards", "blue") + " (a few seconds)")
    settings, found = await finder.locate(settings, client)
    for f in found.values():
        print(f"  {paint('OK ', 'green') if f.ok else paint('X  ', 'red')} {f.line()}")
        if not f.ok:
            print(f"       {paint('fix:', 'yellow')} {f.fix}")
    return settings if all(f.ok for f in found.values()) else None


def _open_mission_control(station: Station, port: int, browser: bool) -> MissionControl | None:
    """Start the mission control page. A busy port is reported, but the run goes on:
    Ctrl+C in the terminal still stops the rover."""
    mc = MissionControl(station, asyncio.get_running_loop(), port)
    try:
        url = mc.start()
    except OSError as e:
        print(
            paint(f"mission control could not start on port {port}: {e}", "red")
            + "\n      fix: close the other Earth Station, or set MISSION_CONTROL_PORT in .env"
            + "\n      until then, press Ctrl+C here to stop the rover"
        )
        return None
    print(f"{paint('mission control', 'blue')} {url}  (STOP button; Ctrl+C here works too)")
    if browser:
        webbrowser.open(url)
    return mc


async def _amain(settings: config.Settings, *, find: bool, browser: bool = True) -> int:
    async with httpx.AsyncClient() as client:
        if find:
            located = await _find(settings, client)
            if located is None:
                print("\nBoards not found. Fix the items marked X and run again.")
                return 1
            settings = located
        log = Logger(settings.log_dir)
        station = Station(settings, client, log)
        if not await station.preflight():
            print("\nPre-flight failed. Fix the items marked X and run again.")
            log.close()
            return 1
        mc = _open_mission_control(station, settings.mission_control_port, browser)
        try:
            await station.run()
        except asyncio.CancelledError:  # Ctrl+C
            pass
        finally:
            await station.land()
            if mc:
                mc.close()
            log.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="earth-station",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--sim", action="store_true", help="run against the built-in fake rover")
    p.add_argument("--suggest", action="store_true", help="never send moves, only log them")
    p.add_argument("--check", action="store_true", help="test every piece, then exit")
    p.add_argument(
        "--live-jev",
        action="store_true",
        help="use the real Jev even with --sim (spends credits, at most JEV_MAX_CALLS per run)",
    )
    p.add_argument(
        "--no-browser",
        action="store_true",
        help="don't open mission control in the browser (its address is still printed)",
    )
    return p


def jev_override(a: argparse.Namespace) -> dict:
    """--sim practice runs are free: they use the pretend Jev unless --live-jev is given."""
    if a.live_jev:
        return {"jev_mode": "live"}
    if a.sim:
        return {"jev_mode": "mock"}
    return {}


def main(argv: list[str] | None = None) -> None:
    a = build_parser().parse_args(argv)

    overrides: dict = {"suggest_only": a.suggest} | jev_override(a)
    if a.sim:
        world = sim.World(mode="jev")
        rover, camera = sim.start(world, token="sim-token", rover_port=0, camera_port=0)
        overrides |= {
            "rover_url": f"http://127.0.0.1:{rover.server_address[1]}",
            "camera_url": f"http://127.0.0.1:{camera.server_address[1]}",
            "rover_cmd_token": "sim-token",
        }

    try:
        settings = config.load(**overrides)
    except config.ConfigError as e:
        sys.exit(f"Settings problem: {e}")

    if a.check:
        results = asyncio.run(check.run_checks(settings, sim=a.sim))
        sys.exit(check.report(results, sim=a.sim))

    try:
        code = asyncio.run(_amain(settings, find=not a.sim, browser=not a.no_browser))
    except KeyboardInterrupt:
        code = 0
    sys.exit(code)


if __name__ == "__main__":
    main()
