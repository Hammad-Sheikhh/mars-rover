# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository.

## Project diary

@PROGRESS.md

`PROGRESS.md` (imported above, so it's loaded every session) records what we did, what we decided, and what's next.

* **At the start of a session:** use it to pick up where we left off, and briefly remind the person where things stand.
* **At the end of a session, or after any meaningful change:** add a new entry at the top of the session log (date, session number, numbered plain-language list of what we did, things to remember). Also update "Where we are now", "Decisions so far" and "Next steps".
* Never put passwords, keys or WiFi names in it. The repo is public.

## How to work with this team (read first)

The team is new to this domain and to GitHub. **Explain as you go.**

* **Before** each step, say in one or two plain sentences what you are about to do and why.
* **After** each step, say what changed and what it means for the team.
* **Explain every git and GitHub operation** as you do it, in everyday words: branch, commit, push, pull, pull request, review, merge, conflict, collaborator, repo visibility, CI checks. Name the button or exact command, and say what the person should see when it works.
* When the person has to do something themselves (on github.com or in a terminal), give numbered click-by-click or command-by-command steps.
* Define technical words the first time you use them. Prefer short analogies over jargon.
* Give one clear recommendation, not a list of options, unless asked to compare.
* Warn before anything hard to undo (making the repo public, force-pushing, deleting branches, merging), and explain the consequence.

## Keep the README current

`README.md` is the project's front page on GitHub. **Every change must update it in the same commit or PR**, so the README always matches the code:

* **Status table:** what works, what's in progress, what's next.
* **Features:** new or changed behaviour of the rover, camera or Earth Station.
* **Project structure:** new, moved or removed files and folders.
* **Quick start / setup:** new steps, settings, commands or requirements.
* **Architecture diagram:** new parts or connections.

If a change truly doesn't affect the README, say so in the PR description. When reporting back, tell the person what changed in the README.

## What this is

Arduino firmware for a two-board Mars rover (both boards upload to Supabase), plus the **Earth Station**: a Python program on a laptop that lets the Jev AI drive the rover over local WiFi.

* `rover1/rover1.ino`: main ESP32. Drives the motors, avoids obstacles, reads sensors, serves a local control page on its own AP, and posts telemetry to Supabase.
* `cam1/cam1.ino`: AI Thinker ESP32-CAM. Serves a live view page on its own AP and uploads JPEGs to Supabase Storage.
* `docs/ARCHITECTURE.md`: system design, pin map, data model, security model and known gaps. **Read it before changing behaviour.**
* `docs/supabase/schema.sql`: recommended tables and RLS policies.
* `earth_station/`: Python ground station. `sim.py` is a fake rover and camera that follows the rover protocol. **`docs/EARTH_STATION.md` defines that protocol (`/sensors/data` fields, `/jev/cmd`)**, so firmware and Python must stay in sync with it.
* `docs/design/`: HTML design pages (open in a browser).

## Build

* Arduino IDE 2.x or `arduino-cli`, with **ESP32 Arduino core 3.x**. The code uses the `ledcAttach(pin, freq, res)` API, which doesn't exist in 2.x.
* Rover board: `esp32:esp32:esp32`. Camera board: `esp32:esp32:esp32cam` (enable PSRAM).
* Rover libraries: `Adafruit BMP280 Library`, `Adafruit Unified Sensor`, `DHT sensor library`, `MPU6050_tockn`.
* Each sketch needs a local `secrets.h`: copy `secrets.example.h` and fill it in.

Compile check (no hardware needed):

```sh
cp rover1/secrets.example.h rover1/secrets.h   # only if you have no secrets.h yet
arduino-cli compile --fqbn esp32:esp32:esp32 rover1
arduino-cli compile --fqbn esp32:esp32:esp32cam cam1
```

CI (`.github/workflows/ci.yml`) compiles both sketches and runs a gitleaks secret scan on every PR.

Firmware has no unit tests and can only be verified on hardware. When you change firmware, say what you could and could not verify.

### Earth Station (Python)

```sh
sh scripts/setup.sh                                    # or: powershell -File scripts\setup.ps1
.venv/bin/python -m pytest -q                          # Windows: .venv\Scripts\python
.venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .
.venv/bin/python -m earth_station --sim                # full loop, no hardware
```

CI runs the setup script, lint and tests on Windows, macOS and Linux.

## Security rules (public repo)

* **Never commit credentials.** WiFi and AP passwords, Supabase URL and keys belong only in `secrets.h` (git-ignored) or `.env` (git-ignored).
* When adding a new credential: add a placeholder to **both** `secrets.example.h` files (if both sketches use it), then reference the macro in the `.ino` file.
* Only the Supabase **anon** key may go on a device. Never use `service_role` in firmware.
* Supabase access control lives in RLS (`docs/supabase/schema.sql`). If the firmware starts writing a new table or column, update `schema.sql` in the same PR.
* Don't print secrets to Serial.
* Earth Station keys (`JEV_API_KEY`, `VISION_API_KEY`, `ROVER_CMD_TOKEN`) live only in the repo-root `.env`. Every setting needs a simulator-friendly default in `config.py` and a line in `.env.example`.
* Never weaken the safety gate (`safety_gate.py`) or the rover's watchdog and vetoes without a test that shows the new behaviour.

## Conventions

* Match the existing style: Arduino C++, `const` pin and tuning constants at the top of the sketch, helper functions below `loop()`, short inline comments.
* Keep `loop()` non-blocking where possible. Use the `millis()` pattern, as `sendDataToSupabase` scheduling does. Avoid adding new `delay()` calls in the rover's main loop.
* Pin changes must update the pin map in `docs/ARCHITECTURE.md`.
* Payload or schema changes must update the data model in `docs/ARCHITECTURE.md` and `docs/supabase/schema.sql`.
* User-facing behaviour changes go in `CHANGELOG.md` under `Unreleased`.
* Python: ruff-formatted, line length 100, type hints, small modules with one job each. Network calls go through `links.py` or `jev_client.py`, and new behaviour gets a test (use `sim.py` for end-to-end tests).
* A protocol change (new telemetry field, new `/jev/cmd` reply) updates `docs/EARTH_STATION.md`, `sim.py` and the firmware together.

## Git workflow

* `main` is protected. Work on a branch, open a PR, and get one review from the other team member.
* Branch names: `feat/...`, `fix/...`, `docs/...`, `chore/...`, `ci/...`.
* Commits use Conventional Commits: `feat(rover): ...`, `fix(cam): ...`, `docs: ...`, `ci: ...`. Scopes are `rover`, `cam`, `station`, `db`, `docs`, `ci`.
* Keep PRs to one concern. Fill in the PR template, including the hardware-test section.
