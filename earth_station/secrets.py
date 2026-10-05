"""Write both boards' secrets.h from .env, so they always match.

python -m earth_station.secrets

.env is the one place you type the hotspot name and password. This helper:
1. makes a long random ROVER_CMD_TOKEN in .env, if there isn't a real one yet;
2. writes rover1/secrets.h and cam1/secrets.h from .env.
Running it again is safe: the token is kept, and the two files are rewritten from .env.
It never prints passwords or the token.
"""

from __future__ import annotations

import re
import secrets
import shutil
import sys
from pathlib import Path

from dotenv import dotenv_values, set_key

from .config import REPO_ROOT

# Values that mean "no real token yet": the simulator default and the template text.
PLACEHOLDER_TOKENS = {"", "sim-token", "change-me-to-a-random-token"}

HEADER = """\
// Made by `python -m earth_station.secrets` from the repo-root .env.
// Don't edit by hand: change .env and run the helper again.
// This file is git-ignored. Never commit it or paste it anywhere public.
#pragma once

// The phone hotspot that the rover, camera and laptop all join
#define WIFI_SSID         {WIFI_SSID}
#define WIFI_PASS         {WIFI_PASS}

// Access point hosted by this board, for its own control page (8+ characters)
#define AP_SSID           {AP_SSID}
#define AP_PASS           {AP_PASS}

// Supabase project settings -> API. The anon (public) key only, never service_role.
#define SUPABASE_URL      {SUPABASE_URL}
#define SUPABASE_ANON_KEY {SUPABASE_ANON_KEY}
"""

ROVER_EXTRA = """
// Shared secret for Jev Auto. Equal to ROVER_CMD_TOKEN in the laptop's .env
#define ROVER_CMD_TOKEN   {ROVER_CMD_TOKEN}
"""

# board folder -> (.env name of its AP name, AP password, default AP name)
BOARDS = {
    "rover1": ("ROVER_AP_SSID", "ROVER_AP_PASS", "ESP32-Car-AP"),
    "cam1": ("CAM_AP_SSID", "CAM_AP_PASS", "ESP32_CAM_MARS"),
}

_DEFINE = re.compile(r'^\s*#define\s+(\w+)\s+"((?:[^"\\]|\\.)*)"', re.MULTILINE)


class SecretsError(Exception):
    """.env is missing something the boards need. The message says what to fix."""


def c_string(value: str) -> str:
    """Quote a value as a C string literal."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def read_defines(path: Path) -> dict[str, str]:
    """The #define NAME "value" lines of a secrets.h, unquoted."""
    text = path.read_text(encoding="utf-8")
    return {name: re.sub(r"\\(.)", r"\1", raw) for name, raw in _DEFINE.findall(text)}


def needs_token(token: str | None) -> bool:
    return (token or "").strip() in PLACEHOLDER_TOKENS


def check_env(env: dict[str, str | None]) -> list[str]:
    """Everything wrong with .env for the real boards, in plain words."""
    problems = []
    if not env.get("WIFI_SSID"):
        problems.append("WIFI_SSID is empty: put your phone hotspot's name in .env")
    if len(env.get("WIFI_PASS") or "") < 8:
        problems.append(
            "WIFI_PASS must be your hotspot password (phones need 8 or more characters)"
        )
    for _, pass_name, _ in BOARDS.values():
        if len(env.get(pass_name) or "") < 8:
            problems.append(
                f"{pass_name} needs 8 or more characters: it's the password you type on "
                "your phone to open that board's own control page"
            )
    for name, value in env.items():
        if value and ("\n" in value or "\r" in value):
            problems.append(f"{name} must be on one line")
    return problems


def render(board: str, env: dict[str, str | None]) -> str:
    ssid_name, pass_name, default_ssid = BOARDS[board]
    values = {
        "WIFI_SSID": env.get("WIFI_SSID") or "",
        "WIFI_PASS": env.get("WIFI_PASS") or "",
        "AP_SSID": env.get(ssid_name) or default_ssid,
        "AP_PASS": env.get(pass_name) or "",
        "SUPABASE_URL": env.get("SUPABASE_URL") or "",
        "SUPABASE_ANON_KEY": env.get("SUPABASE_ANON_KEY") or "",
        "ROVER_CMD_TOKEN": env.get("ROVER_CMD_TOKEN") or "",
    }
    quoted = {k: c_string(v) for k, v in values.items()}
    text = HEADER.format(**quoted)
    if board == "rover1":
        text += ROVER_EXTRA.format(**quoted)
    return text


def write_if_changed(path: Path, text: str) -> str:
    """Write the file. Returns what happened, for the person to read."""
    if path.exists():
        if path.read_text(encoding="utf-8") == text:
            return "unchanged"
        shutil.copyfile(path, path.with_name(path.name + ".bak"))
        path.write_text(text, encoding="utf-8")
        return "updated (the old one is saved as secrets.h.bak)"
    path.write_text(text, encoding="utf-8")
    return "created"


def make_secrets(root: Path = REPO_ROOT) -> list[str]:
    """Check .env, make the token if needed, write both secrets.h. Returns report lines."""
    env_path = root / ".env"
    if not env_path.exists():
        raise SecretsError("No .env file yet. Run the setup script first (see the README).")
    env = dotenv_values(env_path)
    problems = check_env(env)
    if problems:
        raise SecretsError(
            "Fix these in .env, then run this again:\n  - " + "\n  - ".join(problems)
        )

    report = []
    if needs_token(env.get("ROVER_CMD_TOKEN")):
        env["ROVER_CMD_TOKEN"] = secrets.token_urlsafe(24)
        set_key(env_path, "ROVER_CMD_TOKEN", env["ROVER_CMD_TOKEN"], quote_mode="never")
        report.append("rover token: made a new random one and saved it in .env")
    else:
        report.append("rover token: kept the one already in .env")

    for board in BOARDS:
        result = write_if_changed(root / board / "secrets.h", render(board, env))
        report.append(f"{board}/secrets.h: {result}")
    return report


def main() -> None:
    try:
        report = make_secrets()
    except SecretsError as e:
        sys.exit(str(e))
    for line in report:
        print(f"  OK  {line}")
    print(
        "\nNext: flash both boards again so they get the new files (README, Quick Start).\n"
        "If someone else flashes the rover, send them rover1/secrets.h privately, never on GitHub."
    )


if __name__ == "__main__":
    main()
