"""Camera + vision bench: measures how reliable the photo pipeline is.

Run it after flashing the camera and before the first combined drive:

    python -m earth_station.bench               # smoke + stamina (the quick check)
    python -m earth_station.bench all           # every phase, including the probes
    python -m earth_station.bench scene         # ground-truth probes, one by one
    python -m earth_station.bench burst         # map where Google's 429s begin

Phases:
  smoke    5 photos: size, capture and describe latencies, and that every answer
           is a valid scene dict.
  stamina  photos on the live cadence for N minutes: how much of the time the
           scene stays inside the freshness window, plus every 429, refusal,
           timeout and bad answer.
  scene    ground-truth probes: place a box, cover the lens, lay a cable - and
           scores what the vision AI answered against what was really there.
  burst    12 calls at 2.5 s spacing (24 a minute, over the free tier's pace),
           then one calm call: finds where rate limiting starts and that the
           normal cadence recovers.

Needs DESCRIBE_MODE=live and a Gemini key for the vision numbers to be real.
DESCRIBE_MODE=mock also works: only the camera numbers are real then, and the
report says so. Every phase logs one JSON line per event into
runs/vision-bench-*.jsonl, in the same style as the driving logs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import httpx

from . import config, finder, links
from .describe import DescribeError, describe
from .logger import Logger, paint

# The vision build is trusted on the rover only after these pass.
CAPTURE_P95_MS = 1000.0
DESCRIBE_P95_MS = 4000.0
SUCCESS_MIN_PERCENT = 98.0  # of describe calls, rate limits excluded
OBSTACLE_MIN_PERCENT = 90.0
CLEAR_SIDE_MIN_PERCENT = 80.0

PHASES = ("smoke", "stamina", "scene", "burst")

# Waits that would block a test; the tests monkeypatch these to ~0.
RATE_LIMIT_REST_S = 5.0  # after a 429: settle Google's per-minute window down
RECOVERY_REST_S = 4.0  # after a burst: return to calm before the recovery call
LINK_REST_S = 2.0  # after the camera failed: give it a beat, then retry


def _probe(
    name: str,
    instruction: str,
    match: Callable[[dict], bool],
    *,
    score: str | None,
    soft: bool = False,
) -> dict[str, Any]:
    return {"name": name, "instruction": instruction, "match": match, "score": score, "soft": soft}


# Ground-truth probes: the person runs the props, the bench scores the answer.
PROBES: tuple[dict[str, Any], ...] = (
    _probe(
        "obstacle 1 m ahead",
        "stand the camera at rover height (~10 cm up), then put anything solid about "
        "1 m straight ahead of the lens.",
        lambda sc: sc["obstacle_ahead"] is True,
        score="obstacle",
    ),
    _probe(
        "clear floor",
        "take the obstacle away: nothing solid within about 1 m of the lens.",
        lambda sc: sc["obstacle_ahead"] is False,
        score="obstacle",
    ),
    _probe(
        "obstacle on the left",
        "put the box about a metre ahead on the left half, and keep the RIGHT side "
        "clearly open for the rover to turn into.",
        lambda sc: sc["clear_side"] in ("right", "both"),
        score="clear_side",
    ),
    _probe(
        "obstacle on the right",
        "mirror it: box about a metre ahead on the right half, LEFT side clearly open.",
        lambda sc: sc["clear_side"] in ("left", "both"),
        score="clear_side",
    ),
    _probe(
        "covered lens",
        "cover the lens completely with your hand or dark cloth.",
        lambda sc: (
            sc["obstacle_ahead"]
            or sc["clear_side"] == "none"
            or any(
                w in sc["summary"].lower()
                for w in ("dark", "blur", "cover", "black", "can't see", "cannot see")
            )
        ),
        score="obstacle",
    ),
    _probe(
        "cable on the floor",
        "lay a dark cable, wire or string on the floor in view.",
        lambda sc: any(
            w in (sc["summary"] + " " + " ".join(sc["hazards"])).lower()
            for w in ("cable", "wire", "string")
        ),
        score=None,  # soft: a miss is reported, not failed - cables are the hard case
        soft=True,
    ),
)


class BenchError(Exception):
    pass


class Bench:
    """Runs the phases, collects per-event metrics and scores them at the end.

    Every event is one JSON line in runs/vision-bench-*.jsonl (same shape as the
    driving logs), so a run can be reviewed after the fact, not just on screen.
    """

    def __init__(
        self,
        s: config.Settings,
        describe_fn: Callable[[bytes, config.Settings], Awaitable[dict]],
        echo: bool = False,  # True: keep the live narration on screen (CLI use)
    ):
        self.s = s
        self.describe_fn = describe_fn
        self.echo = echo
        s.log_dir.mkdir(parents=True, exist_ok=True)
        self.path = s.log_dir / f"vision-bench-{datetime.now():%Y-%m-%d_%H%M%S}.jsonl"
        self._file = self.path.open("a", encoding="utf-8")
        self.events: list[dict[str, Any]] = []

    def close(self) -> None:
        self._file.close()

    def record(self, kind: str, **data: Any) -> None:
        event = {"t": time.time(), "kind": kind, **data}
        self.events.append(event)
        self._file.write(json.dumps(event) + "\n")
        self._file.flush()

    def say(self, message: str, color: str | None = None) -> None:
        if self.echo:
            description = paint(message, color) if color else message
            print(description)

    def say_ok(self, ok: bool, message: str) -> None:
        if self.echo:
            mark = paint("OK ", "green") if ok else paint("X  ", "red")
            print(f"  {mark} {message}")

    # ---------------- one photo + one description ----------------

    async def cycle(self, camera: links.CameraLink) -> dict[str, Any]:
        """Capture + describe once; raises the real error if either leg fails."""
        start = time.perf_counter()
        photo = await camera.capture()
        capture_ms = (time.perf_counter() - start) * 1000
        begin = time.perf_counter()
        scene = await self.describe_fn(photo, self.s)
        return {
            "kb": round(len(photo) / 1024, 1),
            "capture_ms": round(capture_ms, 1),
            "describe_ms": round((time.perf_counter() - begin) * 1000, 1),
            "scene": scene,
        }

    # ---------------- phases ----------------

    async def smoke(self, camera: links.CameraLink, n: int = 5) -> dict[str, Any]:
        self.say(f"smoke: {n} photos on the current settings", "blue")
        oks: list[dict[str, Any]] = []
        fails: list[str] = []
        for i in range(n):
            try:
                cyc = await self.cycle(camera)
            except (links.LinkError, DescribeError) as e:
                fails.append(f"photo {i + 1}: {e}")
                self.record("bench_error", phase="smoke", message=str(e))
                self.say_ok(False, f"photo {i + 1} failed: {e}")
                continue
            oks.append(cyc)
            self.record("bench_cycle", phase="smoke", **cyc)
            self.say_ok(
                True,
                f"photo {i + 1} | {cyc['kb']} KB | capture {cyc['capture_ms']:.0f} ms "
                f"| describe {cyc['describe_ms']:.0f} ms | '{cyc['scene']['summary'][:60]}'",
            )
        return {"oks": oks, "fails": fails}

    async def stamina(self, camera: links.CameraLink, minutes: float) -> dict[str, Any]:
        """Cycle on the live cadence until the deadline, but always at least once."""
        self.say(f"stamina: describing on the live cadence for {minutes:g} min", "blue")
        end = time.time() + minutes * 60
        rate_limits = refused = other_errors = link_errors = 0
        cycles: list[dict[str, Any]] = []
        fresh_s = 0.0
        span = 0.0
        prev = time.time()
        while time.time() < end or not cycles:
            try:
                cyc = await self.cycle(camera)
            except links.LinkError as e:
                link_errors += 1
                self.record("bench_error", phase="stamina", message=str(e))
                self.say_ok(False, f"camera failed: {e}")
                await asyncio.sleep(LINK_REST_S)
                prev = time.time()
                continue
            except DescribeError as e:
                self.record("bench_error", phase="stamina", message=str(e))
                self.say_ok(False, str(e))
                if "rate limit" in str(e):
                    rate_limits += 1
                    await asyncio.sleep(RATE_LIMIT_REST_S)
                elif "declined" in str(e):
                    refused += 1
                else:
                    other_errors += 1
                prev = time.time()
                continue
            now = time.time()
            period = now - prev
            span += period
            prev = now
            fresh_s += min(period, self.s.scene_max_age_ms / 1000)
            cycles.append(cyc)
            self.record(
                "bench_cycle",
                phase="stamina",
                period_ms=round(period * 1000, 1),
                **cyc,
            )
            self.say(f"   {cyc['describe_ms']:.0f} ms | '{cyc['scene']['summary'][:50]}'", "dim")
            await asyncio.sleep(self.s.camera_every_ms / 1000)
        return {
            "cycles": cycles,
            "rate_limits": rate_limits,
            "refused": refused,
            "other_errors": other_errors,
            "link_errors": link_errors,
            "fresh_percent": round(100.0 * fresh_s / span, 1) if span else 0.0,
            "span_s": round(span, 1),
        }

    async def one_probe(self, camera: links.CameraLink, n: int) -> dict[str, Any]:
        """One probe, no waiting for Enter -- for remote runs (--probe N)."""
        if not 1 <= n <= len(PROBES):
            raise BenchError(f"probe {n} out of range (1-{len(PROBES)})")
        probe = PROBES[n - 1]
        self.say(f"\nprobe: {probe['name']}", "blue")
        self.say(f"  {probe['instruction']}")
        try:
            cyc = await self.cycle(camera)
        except (links.LinkError, DescribeError) as e:
            self.record("bench_probe", phase="scene", name=probe["name"], ok=False, message=str(e))
            self.say(f"  failed: {e}", "red")
            return {
                "name": probe["name"],
                "ok": False,
                "soft": probe["soft"],
                "score": probe["score"],
            }
        hit = bool(probe["match"](cyc["scene"]))
        self.record(
            "bench_probe",
            phase="scene",
            name=probe["name"],
            ok=hit,
            score=probe["score"],
            scene=cyc["scene"],
            describe_ms=cyc["describe_ms"],
        )
        mark = paint("right", "green") if hit else paint("wrong", "red")
        self.say(f"  {probe['name']}: {mark} -> '{cyc['scene']['summary'][:70]}'")
        return {"name": probe["name"], "ok": hit, "soft": probe["soft"], "score": probe["score"]}

    async def scene(self, camera: links.CameraLink) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for i, _probe in enumerate(PROBES, start=1):
            results.append(await self.one_probe(camera, i))
            if i < len(PROBES):
                input("\n  press Enter when the next one is set up... ")
        return {"probes": results}

    async def burst(
        self, camera: links.CameraLink, calls: int = 12, every_s: float = 2.5
    ) -> dict[str, Any]:
        self.say(f"burst: {calls} calls {every_s:g} s apart, then one calm call", "blue")
        first_429: int | None = None
        last_ok = 0
        for i in range(1, calls + 1):
            try:
                cyc = await self.cycle(camera)
            except links.LinkError as e:
                self.record("bench_burst", i=i, ok=False, message=str(e))
                self.say_ok(False, f"call {i}: camera failed: {e}")
            except DescribeError as e:
                self.record("bench_burst", i=i, ok=False, message=str(e))
                if first_429 is None and "rate limit" in str(e):
                    first_429 = i
                self.say_ok(False, f"call {i}: {e}")
            else:
                last_ok = i
                self.record("bench_burst", i=i, ok=True, describe_ms=cyc["describe_ms"])
                self.say_ok(True, f"call {i} ok ({cyc['describe_ms']:.0f} ms)")
            if i < calls:
                await asyncio.sleep(every_s)
        await asyncio.sleep(RECOVERY_REST_S)  # back to the calm cadence
        recovered = False
        try:
            await self.cycle(camera)
            recovered = True
        except (links.LinkError, DescribeError) as e:
            self.record("bench_burst", i="recovery", ok=False, message=str(e))
        self.record("bench_burst", i="recovery", ok=recovered)
        return {"calls": calls, "first_429": first_429, "last_ok": last_ok, "recovered": recovered}

    # ---------------- scoring ----------------

    def verdict(self, data: dict[str, Any]) -> list[tuple[str, bool, str]]:
        rows: list[tuple[str, bool, str]] = []

        latencies = [c for key in ("oks", "cycles") for c in data.get(key, [])]
        real_vision = data.get("real_vision", False)

        cap = [c["capture_ms"] for c in latencies]
        if cap:
            v = _percentile(cap, 95)
            rows.append(
                (f"capture p95 ms (<{CAPTURE_P95_MS:.0f})", v <= CAPTURE_P95_MS, f"{v:.0f} ms")
            )
        des = [c["describe_ms"] for c in latencies]
        if des and real_vision:
            v = _percentile(des, 95)
            rows.append(
                (f"describe p95 ms (<{DESCRIBE_P95_MS:.0f})", v <= DESCRIBE_P95_MS, f"{v:.0f} ms")
            )

        if data.get("fails"):
            rows.append(("every smoke photo answered", False, "; ".join(data["fails"][:2])))

        if real_vision:
            st = data.get("stamina", {})
            n = len(st.get("cycles", []))
            if n:
                bad = st["rate_limits"] + st["refused"] + st["other_errors"] + st["link_errors"]
                pct = 100.0 * n / (n + bad)
                rows.append(
                    (
                        f"describe success ({SUCCESS_MIN_PERCENT:.0f}% min)",
                        pct >= SUCCESS_MIN_PERCENT,
                        f"{pct:.0f}% of {n + bad} calls",
                    )
                )
                rows.append(
                    (
                        "scene freshness on the live cadence",
                        True,
                        f"{st['fresh_percent']:.0f}% inside the {_age_window(self.s):g} s window",
                    )
                )

        probes = data.get("probes", {}).get("probes", [])
        for key, limit, label in (
            ("obstacle", OBSTACLE_MIN_PERCENT, "obstacle probes right"),
            ("clear_side", CLEAR_SIDE_MIN_PERCENT, "clear-side probes right"),
        ):
            xs = [p for p in probes if p["score"] == key]
            if xs:
                pct = 100.0 * sum(p["ok"] for p in xs) / len(xs)
                rows.append(
                    (f"{label} ({limit:.0f}% min)", pct >= limit, f"{pct:.0f}% of {len(xs)}")
                )

        for p in probes:
            if p["soft"]:
                rows.append(
                    (
                        "cable seen (soft check, not scored)",
                        p["ok"],
                        "found" if p["ok"] else "missed",
                    )
                )

        b = data.get("burst", {})
        if b.get("first_429"):
            rows.append(
                (
                    f"rate limit begins at burst call {b['first_429']} (over the free pace)",
                    True,
                    "informational",
                )
            )
            rows.append(
                (
                    "calm cadence recovers after a burst",
                    b.get("recovered", False),
                    "recovered" if b.get("recovered") else "still broken",
                )
            )
        return rows


def _percentile(values: list[float], pct: float) -> float:
    xs = sorted(values)
    k = min(len(xs) - 1, max(0, round((pct / 100) * len(xs)) - 1))
    return float(xs[k])


def _age_window(s: config.Settings) -> float:
    """The scene freshness window in seconds (settings hold milliseconds)."""
    return s.scene_max_age_ms / 1000


def report(bench: Bench, data: dict[str, Any]) -> str:
    rows = bench.verdict(data)
    lines = ["", f"bench report ({bench.path.name})"]
    for text, ok, value in rows:
        mark = paint("PASS", "green") if ok else paint("FAIL", "red")
        lines.append(f"  {mark} {text}: {value}")
    if not data.get("real_vision"):
        lines.append(
            f"  {paint('NOTE', 'yellow')} DESCRIBE_MODE=mock: scene answers above "
            "are the offline stand-in, not real vision."
        )
    # Soft checks are shown but never decide the overall verdict.
    scored = [ok for text, ok, _ in rows if "(soft check" not in text]
    passed = bool(scored) and all(scored)
    lines.append(
        f"  => {paint('ALL THRESHOLDS PASS', 'green') if passed else 'SEE THE FAIL ROWS ABOVE'}"
    )
    return "\n".join(lines)


async def run(argv: list[str] | None = None) -> int:
    """The real CLI: finds the camera (same finder as the station) and runs phases."""
    p = argparse.ArgumentParser(
        prog="python -m earth_station.bench",
        description="Measure camera + vision reliability before placing the camera on the rover.",
    )
    p.add_argument(
        "phases",
        nargs="*",
        default=None,
        choices=list(PHASES) + ["all"],
        help="phases to run (default: smoke stamina; 'all' adds scene and burst)",
    )
    p.add_argument("--minutes", type=float, default=3.0, help="stamina phase length (default 3)")
    p.add_argument(
        "--probe",
        type=int,
        default=None,
        metavar="N",
        help="run only ground-truth probe N (1-based), with no Enter-waiting",
    )
    args = p.parse_args(argv)
    given = args.phases or ["smoke", "stamina"]
    phases = list(PHASES) if "all" in given else list(given)

    s = config.load()
    real_vision = s.describe_mode == "live"
    data: dict[str, Any] = {"real_vision": real_vision}
    async with httpx.AsyncClient() as client:
        s, found = await finder.locate(s, client, boards=("camera",))
        if not found["camera"].ok:
            raise BenchError(
                f"camera not found: {found['camera'].line()}  fix: {found['camera'].fix}"
            )
        screen = Logger(s.log_dir)
        screen.info(
            f"bench {', '.join(phases)} | camera {s.camera_url} "
            f"| vision {s.describe_mode}/{s.vision_provider} '{s.vision_model}'"
        )
        camera = links.CameraLink(client, s.camera_url)
        bench = Bench(s, describe, echo=True)
        try:
            if args.probe:
                result = await bench.one_probe(camera, args.probe)
                print(
                    f"  probe '{result['name']}': {'OK' if result['ok'] else 'missed'} "
                    f"({bench.path.name})"
                )
                return 0
            if "smoke" in phases:
                smoke = await bench.smoke(camera)
                data["oks"], data["fails"] = smoke["oks"], smoke["fails"]
            if "stamina" in phases:
                data["stamina"] = await bench.stamina(camera, args.minutes)
            if "scene" in phases:
                data["probes"] = await bench.scene(camera)
            if "burst" in phases:
                data["burst"] = await bench.burst(camera)
            print(report(bench, data))
        finally:
            bench.close()
            screen.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
