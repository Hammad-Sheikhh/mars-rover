"""Look up a board's `.local` name (e.g. `rover.local`) ourselves, with mDNS.

mDNS is DNS shouted on the local network: we send "who is rover.local?" to the
mDNS group address and the board answers with its IP. Doing it here means the
Earth Station doesn't depend on the laptop's operating system supporting `.local`.
If our own question gets no answer, we still ask the operating system as a backup.
"""

from __future__ import annotations

import asyncio
import socket
import struct
import time

MDNS_GROUP = ("224.0.0.251", 5353)
TYPE_A = 1  # an IPv4 address record
CLASS_IN = 1
UNICAST_REPLY = 0x8000  # "please answer me directly", set on the question's class


def build_query(name: str) -> bytes:
    """A DNS question for the IPv4 address of `name` (e.g. "rover.local")."""
    header = struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0)
    return header + _encode_name(name) + struct.pack(">HH", TYPE_A, CLASS_IN | UNICAST_REPLY)


def parse_addresses(packet: bytes, name: str) -> list[str]:
    """The IPv4 addresses for `name` in a DNS reply. Anything unreadable gives []."""
    try:
        _, flags, qd, an, ns, ar = struct.unpack_from(">HHHHHH", packet)
        if not flags & 0x8000:  # a question from someone else, not an answer
            return []
        pos = 12
        for _ in range(qd):
            _, pos = _read_name(packet, pos)
            pos += 4
        found = []
        for _ in range(an + ns + ar):
            rname, pos = _read_name(packet, pos)
            rtype, rclass, _, rlen = struct.unpack_from(">HHIH", packet, pos)
            pos += 10
            rdata = packet[pos : pos + rlen]
            pos += rlen
            same = rname.lower() == name.lower()
            if same and rtype == TYPE_A and rclass & 0x7FFF == CLASS_IN and rlen == 4:
                found.append(socket.inet_ntoa(rdata))
        return found
    except (struct.error, IndexError, UnicodeDecodeError):
        return []


def ask(name: str, timeout: float = 1.5, server: tuple[str, int] = MDNS_GROUP) -> str | None:
    """Send the question and wait up to `timeout` seconds for an answer. Blocking."""
    query = build_query(name)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
            sock.bind(("", 0))
            sock.sendto(query, server)
            deadline = time.monotonic() + timeout
            while (left := deadline - time.monotonic()) > 0:
                sock.settimeout(left)
                packet, _ = sock.recvfrom(4096)
                addresses = parse_addresses(packet, name)
                if addresses:
                    return addresses[0]
    except OSError:  # includes the timeout; also no network at all
        pass
    return None


def ask_os(name: str) -> str | None:
    """The operating system's own lookup (works for .local on most Macs and Windows 10+)."""
    try:
        infos = socket.getaddrinfo(name, 80, socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return None
    return infos[0][4][0] if infos else None


async def resolve(name: str, timeout: float = 1.5) -> str | None:
    """The IPv4 address of `name`, or None. Our own mDNS question first, then the OS."""
    ip = await asyncio.to_thread(ask, name, timeout)
    if ip:
        return ip
    try:
        return await asyncio.wait_for(asyncio.to_thread(ask_os, name), timeout=2.0)
    except TimeoutError:
        return None


def _encode_name(name: str) -> bytes:
    return b"".join(bytes([len(p)]) + p.encode() for p in name.split(".") if p) + b"\x00"


def _read_name(packet: bytes, pos: int) -> tuple[str, int]:
    """Read a (possibly compressed) DNS name. Returns the name and the position after it."""
    labels: list[str] = []
    end = None  # where to continue after the first compression pointer
    for _ in range(64):  # a guard against pointer loops
        length = packet[pos]
        if length & 0xC0 == 0xC0:  # pointer to a name earlier in the packet
            if end is None:
                end = pos + 2
            pos = ((length & 0x3F) << 8) | packet[pos + 1]
        elif length == 0:
            return ".".join(labels), end if end is not None else pos + 1
        else:
            labels.append(packet[pos + 1 : pos + 1 + length].decode())
            pos += 1 + length
    raise IndexError("DNS name too long")
