from earth_station import safety_gate
from earth_station.jev_client import Decision
from earth_station.whiteboard import Whiteboard


def board_in_jev(distance=100):
    b = Whiteboard()
    b.post_telemetry({"mode": "jev", "distance_cm": distance, "pitch": 0, "roll": 0})
    b.post_scene({"summary": "open", "obstacle_ahead": False, "clear_side": "both", "hazards": []})
    return b


def decision(action="forward", confidence=0.9, blocked=0.1):
    return Decision(action, confidence, {action: confidence}, blocked, 100.0)


def test_approves_confident_move_with_limits(settings):
    r = safety_gate.check(decision("turn_right"), board_in_jev(), settings)
    assert r.approved
    assert r.command["action"] == "turn_right"
    assert r.command["speed"] == settings.max_speed
    assert r.command["duration_ms"] == settings.move_ms


def test_sends_nothing_outside_jev_mode(settings):
    b = board_in_jev()
    b.telemetry["mode"] = "manual"
    r = safety_gate.check(decision(), b, settings)
    assert r.command is None


def test_firmware_without_mode_field_never_drives(settings):
    b = board_in_jev()
    del b.telemetry["mode"]
    assert safety_gate.check(decision(), b, settings).command is None


def test_unsure_jev_means_stop(settings):
    r = safety_gate.check(decision(confidence=0.5), board_in_jev(), settings)
    assert not r.approved and r.command["action"] == "stop"


def test_forward_into_flagged_obstacle_means_stop(settings):
    r = safety_gate.check(decision("forward", blocked=0.9), board_in_jev(), settings)
    assert r.command["action"] == "stop"
    assert "blocked" in r.reason


def test_turn_allowed_even_when_blocked(settings):
    r = safety_gate.check(decision("turn_left", blocked=0.9), board_in_jev(), settings)
    assert r.approved and r.command["action"] == "turn_left"


def test_no_jev_answer_means_stop(settings):
    r = safety_gate.check(None, board_in_jev(), settings)
    assert r.command["action"] == "stop"


def test_stale_telemetry_means_stop(settings):
    b = board_in_jev()
    b.telemetry_at -= settings.telemetry_max_age_ms + 100
    assert safety_gate.check(decision(), b, settings).reason == "telemetry too old"


def test_stale_scene_means_stop(settings):
    b = board_in_jev()
    b.scene_at -= settings.scene_max_age_ms + 100
    assert safety_gate.check(decision(), b, settings).reason == "camera description too old"


def test_sequence_numbers_increase(settings):
    b = board_in_jev()
    a = safety_gate.check(decision(), b, settings).command["seq"]
    c = safety_gate.check(decision(), b, settings).command["seq"]
    assert c == a + 1
