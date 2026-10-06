import pytest

from earth_station import config


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """Default (simulator) settings, isolated from the developer's own .env."""
    for name in (
        "JEV_MODE",
        "DESCRIBE_MODE",
        "VISION_API_KEY",
        "VISION_MODEL",
        "VISION_EFFORT",
        "VISION_TIMEOUT_S",
        "ROVER_URL",
        "CAMERA_URL",
        "ROVER_CMD_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    return config.load(env_file=tmp_path / "missing.env", log_dir=tmp_path / "runs")
