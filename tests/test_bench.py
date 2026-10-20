"""The bench itself: metrics, probes and scoring, with fake camera and vision."""

import asyncio
import json
from dataclasses import replace

import pytest

from earth_station import config
from earth_station.bench import Bench, BenchError, _percentile, report
from earth_station.describe import DescribeError
from earth_station.links import LinkError

PHOTO = b"\xff\xd8\xff\xe0 pretend jpeg \xff\xd9"
SCENE = {
    "summary": "Table leg about 40 cm ahead. Open floor to the right.",
    "obstacle_ahead": True,
    "clear_side": "right",
    "hazards": ["cable on floor"],
}


class FakeCamera:
    """Answers like the camera link; each item is bytes or an exception."""

    def __init__(self, items=None):
        self.items = list(items or [])
        self.calls = 0

    async def capture(self) -> bytes:
        item = self.items[self.calls] if self.calls < len(self.items) else PHOTO
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


def fake_describe(answers=None):
    """A describe() stand-in: pops one answer per call, SCENE when the list runs out."""

    async def fn(jpeg: bytes, settings: config.Settings) -> dict:
        if answers:
            item = answers.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return SCENE

    return fn


@pytest.fixture
def live(settings):
    return replace(
        settings,
        describe_mode="live",
        vision_api_key="test-key",
        camera_every_ms=10,
        scene_max_age_ms=1000,
    )


def total(data, key):
    return data[key]


# ------------------------------- smoke ---------------------------------------


def test_smoke_records_every_photo_and_writes_the_log(live):
    b = Bench(live, fake_describe(), echo=False)
    out = asyncio.run(b.smoke(FakeCamera(), n=3))
    assert len(out["oks"]) == 3
    assert out["oks"][0]["kb"] == round(len(PHOTO) / 1024, 1)
    assert out["oks"][0]["scene"] == SCENE
    files = list(live.log_dir.glob("vision-bench-*.jsonl"))
    assert files and all(
        json.loads(line)["kind"] == "bench_cycle" for line in files[0].read_text().splitlines()
    )


def test_smoke_counts_camera_and_vision_failures(live):
    b = Bench(live, fake_describe(), echo=False)
    out = asyncio.run(b.smoke(FakeCamera(items=[LinkError("boom"), LinkError("cough")]), n=2))
    assert out["oks"] == [] and len(out["fails"]) == 2

    b = Bench(
        live,
        fake_describe(answers=[DescribeError("vision AI declined to describe this photo")]),
        echo=False,
    )
    out = asyncio.run(b.smoke(FakeCamera(items=[PHOTO, PHOTO]), n=2))
    assert len(out["fails"]) == 1 and "declined" in out["fails"][0]
    assert len(out["oks"]) == 1


# ------------------------------- stamina -------------------------------------


def test_stamina_always_runs_one_cycle_and_counts_rate_limits(live, monkeypatch):
    monkeypatch.setattr("earth_station.bench.RATE_LIMIT_REST_S", 0.01)
    rate = DescribeError("vision AI rate limit reached; try a bigger CAMERA_EVERY_MS")
    b = Bench(live, fake_describe(answers=[rate]), echo=False)
    out = asyncio.run(b.stamina(FakeCamera(), minutes=0.003))
    assert out["rate_limits"] == 1
    assert len(out["cycles"]) >= 1
    assert 0 < out["fresh_percent"] <= 100
    errors = [e for e in b.events if e["kind"] == "bench_error"]
    assert errors and "rate limit" in errors[0]["message"]


def test_stamina_counts_camera_link_failures_without_dying(live):
    b = Bench(live, fake_describe(), echo=False)
    cam = FakeCamera(items=[LinkError("camera dead")] * 3)
    out = asyncio.run(b.stamina(cam, minutes=0.001))
    assert out["link_errors"] == cam.calls - len(out["cycles"]) or out["link_errors"] >= 1
    assert len(out["cycles"]) >= 1


# ------------------------------- scene ---------------------------------------


def test_scene_probes_are_scorable_and_recorded(live, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *a: "")
    b = Bench(live, fake_describe(), echo=False)
    out = asyncio.run(b.scene(FakeCamera()))
    names = [p["name"] for p in out["probes"]]
    assert len(names) == 6
    assert names[:2] == ["obstacle 1 m ahead", "clear floor"]
    hits = [p["ok"] for p in out["probes"]]
    # SCENE says obstacle ahead + right side open + cable hazard, so:
    assert hits == [True, False, True, False, True, True]
    recorded = [e for e in b.events if e["kind"] == "bench_probe"]
    assert all(e["scene"] == SCENE for e in recorded)


def test_one_probe_scores_one_probe_and_never_waits_for_input(live):
    """--probe N: a remote caller fires one probe themselves; no Enter at all."""
    b = Bench(live, fake_describe(), echo=False)
    result = asyncio.run(b.one_probe(FakeCamera(), 1))
    recorded = [e for e in b.events if e["kind"] == "bench_probe"]
    assert result == {"name": "obstacle 1 m ahead", "ok": True, "soft": False, "score": "obstacle"}
    assert len(recorded) == 1 and recorded[0]["ok"] is True


def test_one_probe_rejects_an_out_of_range_number(live):
    b = Bench(live, fake_describe(), echo=False)
    with pytest.raises(BenchError, match="out of range"):
        asyncio.run(b.one_probe(FakeCamera(), 0))
    with pytest.raises(BenchError, match="out of range"):
        asyncio.run(b.one_probe(FakeCamera(), 99))


def test_one_probe_counts_a_failed_capture_as_a_miss(live):
    b = Bench(
        live, fake_describe(answers=[DescribeError("vision AI rate limit reached")]), echo=False
    )
    result = asyncio.run(b.one_probe(FakeCamera(), 1))
    assert result["ok"] is False
    recorded = [e for e in b.events if e["kind"] == "bench_probe"]
    assert recorded and "rate limit" in recorded[0]["message"]


# ------------------------------- burst ---------------------------------------


def test_burst_finds_the_first_rate_limit_and_recovers(live, monkeypatch):
    monkeypatch.setattr("earth_station.bench.RECOVERY_REST_S", 0.01)
    rate = DescribeError("vision AI rate limit reached")
    answers = [SCENE, rate, SCENE, rate, SCENE, rate, SCENE, rate, SCENE, rate, SCENE, rate]
    b = Bench(live, fake_describe(answers=answers), echo=False)
    out = asyncio.run(b.burst(FakeCamera(), calls=12, every_s=0))
    assert out["first_429"] == 2 and out["last_ok"] == 11 and out["recovered"] is True
    kinds = [e for e in b.events if e["kind"] == "bench_burst"]
    assert kinds[-1]["i"] == "recovery" and kinds[-1]["ok"] is True


def test_burst_stays_clean_when_all_answers_succeed(live, monkeypatch):
    monkeypatch.setattr("earth_station.bench.RECOVERY_REST_S", 0.01)
    b = Bench(live, fake_describe(), echo=False)
    out = asyncio.run(b.burst(FakeCamera(), calls=4, every_s=0))
    assert out["first_429"] is None and out["recovered"] is True


# ------------------------------- scoring -------------------------------------


def test_percentile_picks_an_actual_data_point():
    assert _percentile([5.0], 95) == 5.0
    assert _percentile([1, 2, 3, 4, 100], 95) == 100.0
    assert _percentile([100, 1, 2, 3, 4], 95) == 100.0


def test_verdict_passes_a_healthy_run(live):
    s = replace(live, scene_max_age_ms=5000)
    b = Bench(s, fake_describe(), echo=False)
    data = {
        "real_vision": True,
        "oks": [{"kb": 30.0, "capture_ms": 150.0, "describe_ms": 2400.0, "scene": SCENE}],
        "cycles": [
            {"kb": 30.0, "capture_ms": 180.0, "describe_ms": 2500.0, "scene": SCENE},
            {"kb": 30.0, "capture_ms": 200.0, "describe_ms": 2600.0, "scene": SCENE},
        ],
        "stamina": {
            "cycles": [1] * 10,
            "rate_limits": 0,
            "refused": 0,
            "other_errors": 0,
            "link_errors": 0,
            "fresh_percent": 95.0,
        },
        "probes": {
            "probes": [
                {"name": "obstacle 1 m ahead", "ok": True, "soft": False, "score": "obstacle"},
                {"name": "clear floor", "ok": True, "soft": False, "score": "obstacle"},
                {"name": "obstacle on the left", "ok": True, "soft": False, "score": "clear_side"},
                {"name": "obstacle on the right", "ok": True, "soft": False, "score": "clear_side"},
                {"name": "covered lens", "ok": True, "soft": False, "score": "obstacle"},
                {"name": "cable on the floor", "ok": False, "soft": True, "score": None},
            ]
        },
    }
    rows = b.verdict(data)
    marks = {text: ok for text, ok, _ in rows}
    assert marks["capture p95 ms (<1000)"] is True
    assert marks["describe p95 ms (<4000)"] is True
    assert marks["describe success (98% min)"] is True
    assert marks["obstacle probes right (90% min)"] is True
    assert marks["clear-side probes right (80% min)"] is True
    assert any("cable" in text and not ok for text, ok, _ in rows)  # soft miss shows, not fails
    assert all(ok for text, ok, _ in rows if "cable" not in text)  # hard rows all pass
    assert "ALL THRESHOLDS PASS" in report(b, data)
    assert "not real vision" not in report(b, data)  # real vision: no mock note


def test_verdict_flags_failures_and_mock_mode(live):
    b = Bench(replace(live, describe_mode="mock"), fake_describe(), echo=False)
    data = {
        "real_vision": False,
        "oks": [{"kb": 30.0, "capture_ms": 1500.0, "describe_ms": 0.0, "scene": SCENE}],
        "fails": ["photo 2: boom", "photo 5: quux"],
    }
    text = report(b, data)
    assert "FAIL capture p95 ms" in text
    assert "every smoke photo answered" in text
    assert "mock" in text and "not real vision" in text
    # a run with fails can't be reported as a full pass
    assert "ALL THRESHOLDS PASS" not in text


def test_report_says_when_nothing_was_scored(live):
    """A burst-only run (or any run without rows) must not claim a verdict."""
    b = Bench(replace(live, describe_mode="mock"), fake_describe(), echo=False)
    text = report(b, {"real_vision": True, "burst": {"first_429": None}})
    assert "NO THRESHOLDS EVALUATED" in text
    assert "ALL THRESHOLDS PASS" not in text
    assert "FAIL" not in text


def test_run_raises_when_the_camera_is_not_found(settings, monkeypatch, tmp_path):
    from earth_station import bench as bench_module
    from earth_station.finder import Found

    def hidden_load(**overrides):
        return replace(settings, describe_mode="mock", log_dir=tmp_path / "runs")

    async def fake_locate(s, client, boards=("rover", "camera")):
        return s, {"camera": Found(board="camera")}  # empty url -> not found

    monkeypatch.setattr(bench_module.config, "load", hidden_load)
    monkeypatch.setattr(bench_module.finder, "locate", fake_locate)
    with pytest.raises(BenchError, match="camera not found"):
        asyncio.run(bench_module.run([]))
