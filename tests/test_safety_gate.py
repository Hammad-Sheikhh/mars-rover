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


def test_unsure_reverse_is_allowed_when_something_is_close(settings):
    """Backing off adds clearance, so the confidence floor does not block it.

    22 Oct: reverse 0.48 at 18 cm left the rover pinned against a stool leg.
    """
    r = safety_gate.check(decision("reverse", confidence=0.48), board_in_jev(distance=18), settings)
    assert r.approved and r.command["action"] == "reverse"
    assert "reversing away" in r.reason


def test_unsure_reverse_far_from_anything_still_stops(settings):
    r = safety_gate.check(
        decision("reverse", confidence=0.48), board_in_jev(distance=120), settings
    )
    assert not r.approved and r.command["action"] == "stop"


def test_unsure_forward_and_turn_are_still_stopped_when_close(settings):
    for action in ("forward", "turn_left", "turn_right"):
        r = safety_gate.check(decision(action, confidence=0.5), board_in_jev(distance=18), settings)
        assert not r.approved, action
        assert r.command["action"] == "stop", action


def test_forward_into_flagged_obstacle_means_stop(settings):
    r = safety_gate.check(decision("forward", blocked=0.9), board_in_jev(), settings)
    assert r.command["action"] == "stop"


def test_forward_is_refused_inside_the_safe_distance(settings):
    """Keep a real gap: the firmware veto is only 20 cm, which is too late.

    22 Oct: the rover pushed into a stool at 18-36 cm because the gate approved
    forward on Jev's guess alone.
    """
    r = safety_gate.check(decision("forward"), board_in_jev(distance=30), settings)
    assert not r.approved and "safe distance" in r.reason
    assert safety_gate.check(decision("forward"), board_in_jev(distance=120), settings).approved


def test_no_echo_counts_as_clear_ahead(settings):
    """distance_cm -1 means "no echo within ~2 m", so the floor ahead is open."""
    assert safety_gate.check(decision("forward"), board_in_jev(distance=-1), settings).approved


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


def test_stale_scene_only_blocks_forward(settings):
    """Turning in place is safe with an old picture; driving forward is not."""
    b = board_in_jev()
    b.scene_at -= settings.scene_max_age_ms + 100

    assert (
        safety_gate.check(decision("forward"), b, settings).reason == "camera description too old"
    )
    turn = safety_gate.check(decision("turn_left"), b, settings)
    assert turn.approved and turn.command["action"] == "turn_left"
    back = safety_gate.check(decision("reverse"), b, settings)
    assert back.approved and back.command["action"] == "reverse"


def test_too_far_since_the_photo_blocks_forward(settings):
    b = board_in_jev()
    for _ in range(settings.scene_max_moves + 1):
        b.note_move("forward")

    forward = safety_gate.check(decision("forward"), b, settings)
    assert not forward.approved and forward.reason == "camera view is out of date"
    assert safety_gate.check(decision("turn_right"), b, settings).approved


def test_sequence_numbers_increase(settings):
    b = board_in_jev()
    a = safety_gate.check(decision(), b, settings).command["seq"]
    c = safety_gate.check(decision(), b, settings).command["seq"]
    assert c == a + 1
