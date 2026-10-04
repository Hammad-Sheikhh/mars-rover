"""HTTP links to the two boards over the local WiFi.

Rover:  GET  /sensors/data  -> telemetry JSON
        POST /jev/cmd       -> {"seq", "action", "speed", "duration_ms"}, header X-Token
Camera: GET  /capture       -> one JPEG
"""

from __future__ import annotations

from typing import Any

import httpx

ACTIONS = ("forward", "turn_left", "turn_right", "reverse", "stop")


class LinkError(Exception):
    """A board did not answer, or answered with something unusable."""


class RoverLink:
    def __init__(self, client: httpx.AsyncClient, base_url: str, token: str):
        self._client = client
        self._base = base_url
        self._token = token

    async def read(self) -> dict[str, Any]:
        try:
            r = await self._client.get(f"{self._base}/sensors/data", timeout=0.8)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise LinkError(f"rover /sensors/data: {e}") from e
        if not isinstance(data, dict):
            raise LinkError("rover /sensors/data did not return a JSON object")
        return data

    async def send(self, command: dict[str, Any]) -> dict[str, Any]:
        if command.get("action") not in ACTIONS:
            raise ValueError(f"unknown action {command.get('action')!r}")
        try:
            r = await self._client.post(
                f"{self._base}/jev/cmd",
                json=command,
                headers={"X-Token": self._token},
                timeout=0.8,
            )
        except httpx.HTTPError as e:
            raise LinkError(f"rover /jev/cmd: {e}") from e
        if r.status_code == 401:
            raise LinkError("rover rejected the token: ROVER_CMD_TOKEN must match rover secrets.h")
        if r.status_code == 404:
            raise LinkError("rover has no /jev/cmd yet: flash firmware with Jev support")
        try:
            return r.json()
        except ValueError as e:
            raise LinkError(f"rover /jev/cmd returned HTTP {r.status_code} without JSON") from e


class CameraLink:
    def __init__(self, client: httpx.AsyncClient, base_url: str):
        self._client = client
        self._base = base_url

    async def capture(self) -> bytes:
        try:
            r = await self._client.get(f"{self._base}/capture", timeout=3.0)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise LinkError(f"camera /capture: {e}") from e
        if not r.content.startswith(b"\xff\xd8"):
            raise LinkError("camera /capture did not return a JPEG")
        return r.content
