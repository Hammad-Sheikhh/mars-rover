"""`python -m earth_station --check`: test every piece and say how to fix what's wrong.

Nothing moves. The only command sent to the rover is `stop`, to test the token.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx
from dotenv import dotenv_values

from . import finder, secrets
from .config import REPO_ROOT, Settings
from .describe import DescribeError, describe
from .jev_client import JevClient, JevError
from .links import CameraLink, LinkError, RoverLink
from .logger import paint

MAKE_SECRETS = "run `python -m earth_station.secrets`, then flash the board again"


@dataclass
class Result:
    ok: bool
    what: str
    fix: str = ""


def file_checks(s: Settings, root: Path = REPO_ROOT) -> list[Result]:
    """.env and both secrets.h: is the hotspot set, and do the boards match the laptop?"""
    env_path = root / ".env"
    if not env_path.exists():
        return [
            Result(False, "no .env settings file", "run the setup script (README, Quick Start)")
        ]
    env = dotenv_values(env_path)
    out = [Result(True, ".env found")]

    problems = secrets.check_env(env)
    out += [Result(False, p, "edit .env, then " + MAKE_SECRETS) for p in problems]
    if not problems:
        out.append(Result(True, "hotspot and board passwords are set in .env"))

    if secrets.needs_token(s.rover_cmd_token):
        out.append(Result(False, "no real rover token in .env yet", MAKE_SECRETS))
    else:
        out.append(Result(True, "rover token is set in .env"))

    for board in secrets.BOARDS:
        path = root / board / "secrets.h"
        if not path.exists():
            out.append(Result(False, f"{board}/secrets.h is missing", MAKE_SECRETS))
            continue
        defines = secrets.read_defines(path)
        expected = {"WIFI_SSID": env.get("WIFI_SSID"), "WIFI_PASS": env.get("WIFI_PASS")}
        if board == "rover1":
            expected["ROVER_CMD_TOKEN"] = s.rover_cmd_token
        different = [k for k, v in expected.items() if v and defines.get(k) != v]
        if different:
            out.append(
                Result(
                    False,
                    f"{board}/secrets.h doesn't match .env ({', '.join(different)})",
                    MAKE_SECRETS,
                )
            )
        else:
            out.append(Result(True, f"{board}/secrets.h matches .env"))
    return out


async def link_checks(s: Settings, client: httpx.AsyncClient) -> list[Result]:
    """Ask the rover, camera and Jev to answer, like the real run would."""
    out = []

    rover = RoverLink(client, s.rover_url, s.rover_cmd_token)
    try:
        t = await rover.read() if s.rover_url else None
    except LinkError:
        out.append(
            Result(
                False,
                f"rover not found at {s.rover_url}",
                "is it switched on and joined to the hotspot? Look for "
                "'WiFi station connected' in its Serial monitor. "
                "Is the laptop on the same hotspot?",
            )
        )
    else:
        if t is None:  # not found: the finder already said so
            pass
        elif "mode" not in t:
            out.append(
                Result(
                    False, "rover firmware has no Jev Auto", "flash rover1 firmware 2.1 or newer"
                )
            )
        else:
            out.append(Result(True, f"rover answering at {s.rover_url} | mode {t['mode']}"))
            try:
                await rover.send({"action": "stop", "speed": 0, "duration_ms": 0})
                out.append(Result(True, "rover accepts the token"))
            except LinkError as e:
                fix = "the rover has a different token from .env: " + MAKE_SECRETS
                if "token" not in str(e):
                    fix = ""
                out.append(Result(False, str(e), fix))

    photo = None
    try:
        if s.camera_url:
            photo = await CameraLink(client, s.camera_url).capture()
            kb = len(photo) / 1024
            out.append(Result(True, f"camera answering at {s.camera_url} | {kb:.1f} KB"))
    except LinkError:
        out.append(
            Result(
                False,
                f"camera not found at {s.camera_url}",
                "is it switched on and joined to the hotspot? Is CAMERA_URL in .env right?",
            )
        )

    if photo is not None:
        try:
            scene = await describe(photo, s)
            out.append(Result(True, f'photo description ({s.describe_mode}): "{scene["summary"]}"'))
        except DescribeError as e:
            out.append(
                Result(
                    False,
                    f"photo description failed: {e}",
                    "check VISION_API_KEY in .env, or set DESCRIBE_MODE=mock",
                )
            )

    if s.jev_mode == "mock":
        out.append(Result(True, "Jev: the pretend Jev (JEV_MODE=mock), no key needed"))
    else:
        try:
            ms = await JevClient(client, s).ping()
            out.append(Result(True, f"Jev answering | {ms:.0f} ms"))
        except JevError as e:
            out.append(
                Result(False, str(e), "check JEV_API_KEY in .env and the internet connection")
            )
    return out


def found_results(found: dict[str, finder.Found]) -> list[Result]:
    """One line per board: where the finder found it, or where it looked."""
    return [Result(f.ok, f.line(), f.fix) for f in found.values()]


async def run_checks(s: Settings, *, sim: bool, root: Path = REPO_ROOT) -> list[Result]:
    results = [] if sim else file_checks(s, root)
    async with httpx.AsyncClient() as client:
        if not sim:
            s, found = await finder.locate(s, client)
            results += found_results(found)
        results += await link_checks(s, client)
    return results


def report(results: list[Result], *, sim: bool) -> int:
    """Print the results. Returns the exit code: 0 if everything is OK."""
    title = "Earth Station check" + (" (simulator: board files skipped)" if sim else "")
    print(paint(title, "blue"))
    for r in results:
        mark = paint("OK ", "green") if r.ok else paint("X  ", "red")
        print(f"  {mark} {r.what}")
        if not r.ok and r.fix:
            print(f"       {paint('fix:', 'yellow')} {r.fix}")
    bad = sum(not r.ok for r in results)
    if bad:
        print(f"\n{bad} problem(s). Fix them from the top down, then run --check again.")
        return 1
    print(f"\nAll {len(results)} checks OK.")
    return 0
