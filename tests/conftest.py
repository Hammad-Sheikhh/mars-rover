import pytest

from earth_station import config


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """Default (simulator) settings, isolated from the developer's own .env."""
    for name in (
        "JEV_MODE",
        "JEV_API_KEY",
        "JEV_MAX_CALLS",
        "DESCRIBE_MODE",
        "VISION_API_KEY",
        "VISION_PROVIDER",
        "VISION_MODEL",
        "VISION_EFFORT",
        "VISION_FOCUS",
        "VISION_TIMEOUT_S",
        "VISION_MAX_CALLS",
        "VISION_REFRESH_MS",
        "VISION_REFRESH_MOVES",
        "VISION_CLOSE_CM",
        "VISION_LOST_STOP_S",
        "SCENE_MAX_AGE_MS",
        "SCENE_MAX_MOVES",
        "TELEMETRY_EVERY_MS",
        "CAMERA_EVERY_MS",
        "DECIDE_EVERY_MS",
        "ROVER_URL",
        "CAMERA_URL",
        "ROVER_CMD_TOKEN",
        "MISSION_CONTROL_PORT",
    ):
        monkeypatch.delenv(name, raising=False)
    return config.load(env_file=tmp_path / "missing.env", log_dir=tmp_path / "runs")
