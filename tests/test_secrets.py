"""The secrets helper: one .env -> both boards' secrets.h, with a generated rover token."""

import pytest
from dotenv import dotenv_values

from earth_station import secrets

GOOD_ENV = """\
WIFI_SSID=Phone Hotspot
WIFI_PASS=hotspot-pass-1
ROVER_AP_PASS=rover-ap-pass
CAM_AP_PASS=cam-ap-pass
SUPABASE_URL=https://example.supabase.co
SUPABASE_ANON_KEY=anon
ROVER_CMD_TOKEN=sim-token
"""


@pytest.fixture
def root(tmp_path):
    (tmp_path / "rover1").mkdir()
    (tmp_path / "cam1").mkdir()
    (tmp_path / ".env").write_text(GOOD_ENV)
    return tmp_path


def test_writes_both_boards_with_the_same_hotspot_and_a_new_token(root):
    secrets.make_secrets(root)

    token = dotenv_values(root / ".env")["ROVER_CMD_TOKEN"]
    assert not secrets.needs_token(token) and len(token) >= 20

    rover = secrets.read_defines(root / "rover1" / "secrets.h")
    cam = secrets.read_defines(root / "cam1" / "secrets.h")
    assert rover["WIFI_SSID"] == cam["WIFI_SSID"] == "Phone Hotspot"
    assert rover["WIFI_PASS"] == cam["WIFI_PASS"] == "hotspot-pass-1"
    assert rover["ROVER_CMD_TOKEN"] == token
    assert "ROVER_CMD_TOKEN" not in cam
    assert rover["AP_SSID"] == "ESP32-Car-AP" and cam["AP_SSID"] == "ESP32_CAM_MARS"


def test_running_again_keeps_the_token_and_the_files(root):
    secrets.make_secrets(root)
    token = dotenv_values(root / ".env")["ROVER_CMD_TOKEN"]

    report = secrets.make_secrets(root)

    assert dotenv_values(root / ".env")["ROVER_CMD_TOKEN"] == token
    assert "kept" in report[0]
    assert report[1:] == ["rover1/secrets.h: unchanged", "cam1/secrets.h: unchanged"]


def test_a_changed_hotspot_rewrites_both_files_and_keeps_a_backup(root):
    secrets.make_secrets(root)
    env = (root / ".env").read_text().replace("Phone Hotspot", "New Phone")
    (root / ".env").write_text(env)

    secrets.make_secrets(root)

    for board in ("rover1", "cam1"):
        assert secrets.read_defines(root / board / "secrets.h")["WIFI_SSID"] == "New Phone"
        backup = root / board / "secrets.h.bak"
        assert secrets.read_defines(backup)["WIFI_SSID"] == "Phone Hotspot"


def test_missing_hotspot_is_refused_and_nothing_is_written(root):
    (root / ".env").write_text(GOOD_ENV.replace("WIFI_SSID=Phone Hotspot", "WIFI_SSID="))

    with pytest.raises(secrets.SecretsError, match="WIFI_SSID"):
        secrets.make_secrets(root)

    assert not (root / "rover1" / "secrets.h").exists()
    assert dotenv_values(root / ".env")["ROVER_CMD_TOKEN"] == "sim-token"


def test_short_ap_password_is_refused(root):
    (root / ".env").write_text(GOOD_ENV.replace("CAM_AP_PASS=cam-ap-pass", "CAM_AP_PASS=short"))
    with pytest.raises(secrets.SecretsError, match="CAM_AP_PASS"):
        secrets.make_secrets(root)


def test_no_env_file_says_run_setup(tmp_path):
    with pytest.raises(secrets.SecretsError, match="setup"):
        secrets.make_secrets(tmp_path)


def test_quotes_and_backslashes_survive_the_c_string(tmp_path):
    value = 'my "fast" wifi \\ 5'
    path = tmp_path / "secrets.h"
    path.write_text(f"#define WIFI_SSID {secrets.c_string(value)}\n")
    assert secrets.read_defines(path) == {"WIFI_SSID": value}
