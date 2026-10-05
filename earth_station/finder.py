"""Find the rover and the camera on the hotspot, so nobody types an IP address.

For each board, in this order, the first hit wins:
  1. the address in .env (ROVER_URL / CAMERA_URL), if one is set
  2. the simulator running on this laptop (python -m earth_station.sim)
  3. its name, rover.local / cam.local (mdns.py)
  4. a scan of the laptop's network: ask every address `GET /id`

A board is only accepted if its `/id` says which board it is, so a scan can't
mistake the camera (or a printer) for the rover.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace

import httpx

from . import mdns
from .config import Settings

NAMES = {"rover": "rover.local", "camera": "cam.local"}
SIM_URLS = {"rover": "http://127.0.0.1:8081", "camera": "http://127.0.0.1:8082"}
SETTING = {"rover": "ROVER_URL", "camera": "CAMERA_URL"}

FIX = {
    "rover": "is it switched on and joined to the hotspot? Look for 'WiFi station connected' "
    "in its Serial monitor. Is the laptop on the same hotspot? If it still isn't found "
    "(some phones keep devices apart), put the IP address the rover prints at boot "
    "in .env as ROVER_URL=http://<that address>",
    "camera": "is it switched on and joined to the hotspot? Until the camera firmware gets "
    "its name (milestone 4), put the IP address its Serial monitor shows at boot "
    "in .env as CAMERA_URL=http://<that address>",
}


@dataclass
class Found:
    board: str
    url: str = ""  # empty: not found
    how: str = ""  # e.g. "rover.local" or "network scan"
    tried: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.url)

    def line(self) -> str:
        if self.ok:
            return f"{self.board} found at {self.url} ({self.how})"
        return f"{self.board} not found (tried {', '.join(self.tried)})"

    @property
    def fix(self) -> str:
        return "" if self.ok else FIX[self.board]


async def board_at(client: httpx.AsyncClient, url: str, timeout: float = 1.0) -> str | None:
    """Which board answers at `url`: "rover", "camera", "" (answers, but no /id) or None."""
    try:
        r = await client.get(f"{url}/id", timeout=timeout)
    except httpx.HTTPError:
        return None
    try:
        board = r.json().get("board") if r.status_code == 200 else None
    except (ValueError, AttributeError):
        board = None
    return board if isinstance(board, str) else ""


async def scan(
    client: httpx.AsyncClient,
    urls: list[str],
    wanted: set[str],
    *,
    timeout: float = 1.0,
    parallel: int = 64,
) -> dict[str, str]:
    """Ask every url for `/id`, many at once. Returns {board: url} for the boards wanted."""
    found: dict[str, str] = {}
    gate = asyncio.Semaphore(parallel)

    async def probe(url: str) -> None:
        async with gate:
            if wanted <= found.keys():  # everything found already: skip the rest
                return
            board = await board_at(client, url, timeout)
        if board in wanted and board not in found:
            found[board] = url

    await asyncio.gather(*(probe(u) for u in urls))
    return found


def laptop_addresses() -> list[str]:
    """The laptop's own IPv4 addresses on real networks (not loopback or link-local)."""
    found = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # sends nothing; just picks the main network
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        found += [info[4][0] for info in infos]
    except OSError:
        pass
    out = []
    for ip in found:
        a = ipaddress.ip_address(ip)
        if a.is_private and not (a.is_loopback or a.is_link_local) and ip not in out:
            out.append(ip)
    return out


def neighbours(ip: str, prefix: int = 24) -> list[str]:
    """Every other address on the laptop's network. Phone hotspots fit in a /24."""
    net = ipaddress.ip_network(f"{ip}/{prefix}", strict=False)
    return [str(h) for h in net.hosts() if str(h) != ip]


def scan_urls(max_networks: int = 3) -> tuple[list[str], list[str]]:
    """The urls to scan, and a short label for each network (e.g. "192.168.43.x")."""
    urls: list[str] = []
    labels: list[str] = []
    for ip in laptop_addresses():
        label = ip.rsplit(".", 1)[0] + ".x"
        if label in labels:
            continue
        if len(labels) == max_networks:
            break
        labels.append(label)
        urls += [f"http://{h}" for h in neighbours(ip)]
    return urls, labels


async def find(
    client: httpx.AsyncClient,
    configured: dict[str, str],
    *,
    resolve: Callable[[str], Awaitable[str | None]] = mdns.resolve,
    sim_urls: dict[str, str] | None = None,
    network: tuple[list[str], list[str]] | None = None,
) -> dict[str, Found]:
    """Find each board in `configured` ({board: url from .env, or ""}).

    `resolve`, `sim_urls` and `network` (urls + labels) are there so tests can
    use the simulator instead of the real network.
    """
    sims = SIM_URLS if sim_urls is None else sim_urls

    async def one(board: str) -> Found:
        f = Found(board)
        url = configured.get(board, "")
        if url:
            if await board_at(client, url) in (board, ""):  # "": older firmware without /id
                f.url, f.how = url, f"{SETTING[board]} in .env"
                return f
            f.tried.append(f"{url} from .env")
        if board in sims:
            if await board_at(client, sims[board], timeout=0.3) == board:
                f.url, f.how = sims[board], "simulator on this laptop"
                return f
            f.tried.append("simulator on this laptop")
        name = NAMES[board]
        host = await resolve(name)
        if host and await board_at(client, f"http://{host}") == board:
            f.url, f.how = f"http://{host}", name
            return f
        f.tried.append(name)
        return f

    found = dict(zip(configured, await asyncio.gather(*map(one, configured)), strict=True))

    missing = {b for b, f in found.items() if not f.ok}
    if missing:
        urls, labels = network if network is not None else scan_urls()
        hits = await scan(client, urls, missing) if urls else {}
        where = f"scan of {len(urls)} addresses on {', '.join(labels)}" if urls else "no network"
        for board in missing:
            f = found[board]
            if board in hits:
                f.url, f.how = hits[board], "network scan"
            else:
                f.tried.append(where)
    return found


async def locate(
    s: Settings, client: httpx.AsyncClient, boards: tuple[str, ...] = ("rover", "camera")
) -> tuple[Settings, dict[str, Found]]:
    """Find the boards and return settings with their addresses filled in."""
    current = {"rover": s.rover_url, "camera": s.camera_url}
    found = await find(client, {b: current[b] for b in boards})
    urls = {f"{b}_url": f.url for b, f in found.items()}
    return replace(s, **urls), found
