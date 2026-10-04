import pytest

from earth_station import state_text
from earth_station.describe import DescribeError, _describe_mock, validate_scene
from earth_station.jev_client import JevError, _parse_choice, _parse_noul
from earth_station.sim import fake_jpeg
from earth_station.whiteboard import Whiteboard


@pytest.mark.parametrize(
    ("cm", "word"),
    [(62, "clear"), (30, "close"), (12, "danger"), (None, "unknown"), (-1, "unknown")],
)
def test_distance_words(cm, word):
    assert word in state_text.describe_distance(cm, 40)


def test_orientation_words():
    assert "level" in state_text.describe_orientation(3, -1)
    assert "tilted" in state_text.describe_orientation(20, 0)
    assert "dangerous" in state_text.describe_orientation(0, -40)


def test_state_text_contains_conclusions_not_just_numbers(settings):
    b = Whiteboard()
    b.post_telemetry(
        {"distance_cm": 62, "pitch": 3, "roll": -1, "vibration": 0.02, "last_event": "Tilt Warning"}
    )
    b.post_scene(
        {
            "summary": "Chair leg ahead.",
            "obstacle_ahead": True,
            "clear_side": "right",
            "hazards": ["cable on floor"],
        }
    )
    text = state_text.build(b, settings)
    assert "62 cm, clear" in text
    assert "Chair leg ahead." in text
    assert "cable on floor" in text
    assert "Tilt Warning" in text
    assert settings.goal in text


def test_parse_choice_accepts_known_shapes():
    for key in ("choice", "probabilities", "distribution"):
        probs = _parse_choice({key: {"forward": 0.7, "stop": 0.3}})
        assert probs["forward"] == 0.7 and probs["turn_left"] == 0.0


def test_parse_choice_rejects_unknown_shape():
    with pytest.raises(JevError):
        _parse_choice({"something": 1})


def test_parse_noul():
    assert _parse_noul({"type": "noul", "noul": 0.81}) == 0.81
    assert _parse_noul(None) is None


def test_validate_scene_rejects_bad_shapes():
    good = {"summary": "x", "obstacle_ahead": False, "clear_side": "both", "hazards": []}
    assert validate_scene(good)["summary"] == "x"
    for bad in (
        {**good, "summary": ""},
        {**good, "summary": "y" * 301},
        {**good, "obstacle_ahead": "yes"},
        {**good, "clear_side": "up"},
        {**good, "hazards": "cable"},
    ):
        with pytest.raises(DescribeError):
            validate_scene(bad)


def test_mock_describe_reads_simulator_scene():
    scene = {"summary": "Box ahead.", "obstacle_ahead": True, "clear_side": "left", "hazards": []}
    assert _describe_mock(fake_jpeg(scene)) == scene
