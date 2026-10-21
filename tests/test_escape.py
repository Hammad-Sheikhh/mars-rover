"""Getting unstuck: reverse once, measure the room, then pivot if it did not help.

The rover's own 20 cm veto refused a forward move on 22 Oct with a stool leg
18 cm ahead, and the gate then refused Jev's reverse at 0.48 confidence, so the
rover sat there. `Station._next_escape_step` drives the manoeuvre; these tests
pin the decision order without needing a board or the network.
"""

import httpx
import pytest

from earth_station import config, station
from earth_station.logger import Logger
from earth_station.whiteboard import Whiteboard


def make_station(tmp_path):
    settings = config.load(env_file=tmp_path / "missing.env", log_dir=tmp_path / "runs")
    log = Logger(tmp_path / "runs")
    return station.Station(settings, httpx.AsyncClient(), log)


def board_with(distance, side="right"):
    b = Whiteboard()
    b.post_telemetry({"mode": "jev", "distance_cm": distance, "pitch": 0, "roll": 0})
    b.post_scene(
        {"summary": "legs ahead", "obstacle_ahead": True, "clear_side": side, "hazards": []}
    )
    return b


def test_full_manoeuvre_reverse_check_then_three_turns(tmp_path):
    st = make_station(tmp_path)
    b = board_with(18)
    st._plan_escape(b)

    assert st._next_escape_step(b) == "reverse"
    # The distance did not improve, so the pivot is the way out.
    assert st._next_escape_step(b) == "turn_right"
    assert st._next_escape_step(b) == "turn_right"
    assert st._next_escape_step(b) == "turn_right"
    assert st._next_escape_step(b) is None
    assert st._escape_phase is None


def test_pivots_toward_the_open_side(tmp_path):
    st = make_station(tmp_path)
    b = board_with(18, side="left")
    st._plan_escape(b)
    assert st._next_escape_step(b) == "reverse"
    assert st._next_escape_step(b) == "turn_left"


def test_reversing_that_gains_room_hands_back_to_jev(tmp_path):
    st = make_station(tmp_path)
    b = board_with(18)
    st._plan_escape(b)
    assert st._next_escape_step(b) == "reverse"
    b.post_telemetry({"mode": "jev", "distance_cm": 60, "pitch": 0, "roll": 0})
    assert st._next_escape_step(b) is None
    assert st._escape_phase is None


def test_no_echo_after_reverse_counts_as_no_gain(tmp_path):
    st = make_station(tmp_path)
    st._plan_escape(board_with(18))
    b = board_with(-1)
    assert st._next_escape_step(b) == "reverse"
    assert st._next_escape_step(b) == "turn_right"


def test_a_second_manoeuvre_can_start_after_the_first(tmp_path):
    st = make_station(tmp_path)
    b = board_with(18)
    st._plan_escape(b)
    while st._next_escape_step(b) is not None:
        pass
    st._plan_escape(b)
    assert st._next_escape_step(b) == "reverse"


def test_gives_up_after_three_manoeuvres_without_room(tmp_path):
    """A corner with furniture on every side is a job for a hand, not a wheel."""
    st = make_station(tmp_path)
    b = board_with(30)
    for _ in range(station.ESCAPE_GIVE_UP):
        st._plan_escape(b)
        while st._next_escape_step(b) is not None:
            pass
    st._plan_escape(b)
    assert st._escape_phase is None and st._escape_steps == []


@pytest.mark.parametrize("refused", ["obstacle_too_close"])
def test_forward_refusal_starts_the_manoeuvre(refused, tmp_path):
    st = make_station(tmp_path)
    assert st._escape_phase is None
