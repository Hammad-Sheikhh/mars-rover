# Changelog

Notable changes to this project. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
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
