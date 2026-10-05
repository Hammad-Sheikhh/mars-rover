# Changelog

Notable changes to this project. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Camera name** (milestone 4, camera firmware 2.1): the camera announces `cam.local` and answers `GET /id` with `{"board": "camera", "firmware": "2.1.0"}`, so the Earth Station finds it without an IP address. At boot the Serial monitor shows whether it joined the hotspot, its IP address, its name, its AP address and the firmware version.
- **Board finder** (milestone 2): the Earth Station, `--check` and `earth_station.drive` find the rover and camera by themselves: the address in `.env`, then a simulator on this laptop, then `rover.local` / `cam.local` (its own mDNS lookup), then a scan of the hotspot that asks each address `GET /id`. When a board isn't found, it says where it looked.
- **Easy setup** (milestone 1): the hotspot name and password go once into `.env` (`WIFI_SSID`, `WIFI_PASS`). `python -m earth_station.secrets` writes both boards' `secrets.h` from it and makes a random rover token. `python -m earth_station --check` tests the settings files, rover, camera and Jev, and says how to fix each problem.
- **Rover Jev Auto mode** (firmware 2.1): a Jev Auto button, `POST /jev/cmd` with an `X-Token` check, a 1.5 s watchdog, tilt and 20 cm forward vetoes, and moves timed with `millis()`. `/sensors/data` adds `distance_cm`, `mode` and `last_event`. New `GET /id`, `GET /startjev`, and the `rover.local` name. The control page shows the obstacle distance. **The rover's `secrets.h` needs a new `ROVER_CMD_TOKEN` line.**
- Simulator answers `GET /id`.
- Live Jev now follows TypeSafe's official API: options sent as a `criteria` map, `model` field, clear errors for a bad key or rate limit. `JEV_API_URL` defaults to the TypeSafe endpoint, so only `JEV_API_KEY` is needed. Tests check it against the documented examples.
- **Earth Station** (`earth_station/`): a laptop ground station that lets Jev drive the rover. It includes a mock Jev, a built-in rover and camera simulator, a suggest-only mode, a laptop-side safety gate and JSONL run logs.
- One-command setup scripts (`scripts/setup.ps1`, `scripts/setup.sh`), `pyproject.toml`, and 26 tests.
- `docs/EARTH_STATION.md` with the rover protocol for Jev Auto (`distance_cm`, `mode`, `POST /jev/cmd`).
- Design pages in `docs/design/`.
- A CI job that runs the setup, lint and tests on Windows, macOS and Linux.
- `CLAUDE.md`, `CONTRIBUTING.md`, `SECURITY.md` and `docs/ARCHITECTURE.md`.
- `docs/supabase/schema.sql` with the recommended tables and RLS policies.
- GitHub CI: compiles both sketches and runs a gitleaks secret scan.
- Issue templates, a PR template, CODEOWNERS and Dependabot for GitHub Actions.

### Changed
- `.env`: one shared `WIFI_SSID`/`WIFI_PASS` replaces `ROVER_WIFI_*` and `CAM_WIFI_*`.
- `ROVER_URL` and `CAMERA_URL` are now optional and empty by default, meaning "find the board".
- README Quick Start reordered: just the laptop, then the real boards, then the real Jev, then Supabase (optional).
- Credentials moved from the `.ino` files into git-ignored `secrets.h` (template: `secrets.example.h`).
- README rewritten for the current hardware-only setup.

### Removed
- n8n AI workflow (`workflows/`) and the web dashboard (`dashboard/`).

## [2.0] - 2026-08-20
### Changed
- Rover PWM migrated to the ESP32 core 3.x `ledcAttach` API.
- Camera falls back to CIF and a DRAM buffer when PSRAM is missing.

## [1.0] - 2026-01-27
### Added
- MPU6050 pitch, roll, vibration and event logging.
- Camera uploads to Supabase Storage.
- Rover telemetry to Supabase.
