# Changelog

Notable changes to this project. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
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
