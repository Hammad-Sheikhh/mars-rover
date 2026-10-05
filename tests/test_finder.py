"""Finding the boards: .env address, simulator, .local name, network scan. No real network."""

import asyncio
import socket
import struct
import threading

import httpx
import pytest
from test_check import free_port

from earth_station import check, finder, mdns, sim


@pytest.fixture
def boards():
    rover, camera = sim.start(sim.World(seed=1), rover_port=0, camera_port=0)
    yield {
        "rover": f"http://127.0.0.1:{rover.server_address[1]}",
        "camera": f"http://127.0.0.1:{camera.server_address[1]}",
    }
    for srv in (rover, camera):
        srv.shutdown()


async def nobody(name):
    return None


def find(configured, **kw):
    kw = {"resolve": nobody, "sim_urls": {}, "network": ([], []), **kw}

    async def go():
        async with httpx.AsyncClient() as client:
            return await finder.find(client, configured, **kw)

    return asyncio.run(go())


def test_address_in_env_is_used(boards):
    found = find(dict(boards))
    assert found["rover"].url == boards["rover"] and found["rover"].how == "ROVER_URL in .env"
    assert found["camera"].ok


def test_env_address_of_the_wrong_board_is_not_trusted(boards):
    found = find({"rover": boards["camera"]})
    assert not found["rover"].ok
    assert boards["camera"] in found["rover"].line()


def test_simulator_on_this_laptop_is_found(boards):
    found = find({"rover": "", "camera": ""}, sim_urls=boards)
    assert all(f.ok and f.how == "simulator on this laptop" for f in found.values())


def test_found_by_name(boards):
    async def resolve(name):  # pretend rover.local answered with the simulator's address
        return boards["rover"].removeprefix("http://") if name == "rover.local" else None

    found = find({"rover": "", "camera": ""}, resolve=resolve)
    assert found["rover"].url == boards["rover"] and found["rover"].how == "rover.local"
    assert not found["camera"].ok and "cam.local" in found["camera"].line()


def test_network_scan_tells_rover_and_camera_apart(boards):
    nothing = f"http://127.0.0.1:{free_port()}"
    urls = [nothing, boards["camera"], nothing, boards["rover"]]
    found = find({"rover": "", "camera": ""}, network=(urls, ["127.0.0.x"]))
    assert found["rover"].url == boards["rover"] and found["rover"].how == "network scan"
    assert found["camera"].url == boards["camera"]


def test_not_found_says_where_it_looked_and_how_to_fix_it():
    nothing = f"http://127.0.0.1:{free_port()}"
    found = find({"rover": ""}, network=([nothing], ["192.168.43.x"]))
    rover = found["rover"]
    assert not rover.ok
    assert "rover.local" in rover.line() and "scan of 1 addresses on 192.168.43.x" in rover.line()
    assert "ROVER_URL" in rover.fix
    [result] = check.found_results(found)
    assert not result.ok and result.fix == rover.fix


def test_neighbours_cover_a_phone_hotspot():
    hosts = finder.neighbours("192.168.43.17")
    assert len(hosts) == 253 and "192.168.43.1" in hosts and "192.168.43.17" not in hosts


# ---------- mDNS (.local names) ----------


def answer(name: str, ip: str, extra_first: bool = False) -> bytes:
    """A DNS reply like an ESP32 sends, using name compression (a pointer to offset 12)."""
    header = struct.pack(">HHHHHH", 0, 0x8400, 1, 2 if extra_first else 1, 0, 0)
    question = mdns._encode_name(name) + struct.pack(">HH", 1, 1)
    record = b"\xc0\x0c" + struct.pack(">HHIH", 1, 0x8001, 120, 4) + socket.inet_aton(ip)
    other = mdns._encode_name("printer.local") + struct.pack(">HHIH", 1, 1, 120, 4) + bytes(4)
    return header + question + (other if extra_first else b"") + record


def test_reply_is_read_including_compressed_names():
    assert mdns.parse_addresses(answer("rover.local", "172.20.10.3"), "rover.local") == [
        "172.20.10.3"
    ]
    assert mdns.parse_addresses(answer("rover.local", "10.0.0.9", True), "ROVER.local") == [
        "10.0.0.9"
    ]


def test_other_names_questions_and_junk_are_ignored():
    assert mdns.parse_addresses(answer("cam.local", "10.0.0.5"), "rover.local") == []
    assert mdns.parse_addresses(mdns.build_query("rover.local"), "rover.local") == []
    assert mdns.parse_addresses(b"\x00\x01garbage", "rover.local") == []


def test_ask_gets_the_answer_from_a_responder():
    responder = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    responder.bind(("127.0.0.1", 0))
    responder.settimeout(3)

    def reply():
        query, sender = responder.recvfrom(512)
        assert b"\x05rover\x05local\x00" in query
        responder.sendto(answer("rover.local", "172.20.10.3"), sender)

    t = threading.Thread(target=reply)
    t.start()
    try:
        assert mdns.ask("rover.local", 2.0, responder.getsockname()) == "172.20.10.3"
    finally:
        t.join()
        responder.close()


def test_ask_gives_up_quietly_when_nobody_answers():
    silent = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    silent.bind(("127.0.0.1", 0))
    try:
        assert mdns.ask("rover.local", 0.2, silent.getsockname()) is None
    finally:
        silent.close()
