"""Send one move to the rover by hand. Build-order step 1: test the plumbing, no AI.

    python -m earth_station.drive forward
    python -m earth_station.drive turn_left --ms 300 --speed 150
    python -m earth_station.drive stop

The rover must be in Jev Auto mode (press the button on its AP page).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

import httpx

from . import config, finder
from .links import ACTIONS


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Send one move to the rover")
    p.add_argument("action", choices=ACTIONS)
    p.add_argument("--ms", type=int, default=300, help="duration, max 500")
    p.add_argument("--speed", type=int, default=170, help="0-255")
    a = p.parse_args(argv)

    try:
        s = config.load()
    except config.ConfigError as e:
        sys.exit(f"Settings problem: {e}")
    s = asyncio.run(_find_rover(s))

    cmd = {
        "seq": int(time.time() * 1000) % 2_000_000_000,
        "action": a.action,
        "speed": 0 if a.action == "stop" else max(0, min(255, a.speed)),
        "duration_ms": 0 if a.action == "stop" else max(0, min(500, a.ms)),
    }
    try:
        r = httpx.post(
            f"{s.rover_url}/jev/cmd", json=cmd, headers={"X-Token": s.rover_cmd_token}, timeout=2.0
        )
    except httpx.HTTPError as e:
        sys.exit(f"Could not reach the rover at {s.rover_url}: {e}")
    print(f"sent    {json.dumps(cmd)}")
    print(f"rover   HTTP {r.status_code} {r.text.strip()}")


async def _find_rover(s: config.Settings) -> config.Settings:
    async with httpx.AsyncClient() as client:
        s, found = await finder.locate(s, client, boards=("rover",))
    rover = found["rover"]
    if not rover.ok:
        sys.exit(f"{rover.line()}\nfix: {rover.fix}")
    print(f"rover   {rover.line()}")
    return s


if __name__ == "__main__":
    main()
