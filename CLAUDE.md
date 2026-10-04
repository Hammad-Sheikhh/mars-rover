# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository.

## What this is

Arduino firmware for a two-board Mars rover. Both boards upload to Supabase. There is no server code or web app in this repo.

* `rover1/rover1.ino`: main ESP32. Drives the motors, avoids obstacles, reads sensors, serves a local control page on its own AP, and posts telemetry to Supabase.
* `cam1/cam1.ino`: AI Thinker ESP32-CAM. Serves a live view page on its own AP and uploads JPEGs to Supabase Storage.
* `docs/ARCHITECTURE.md`: system design, pin map, data model, security model and known gaps. **Read it before changing behaviour.**
* `docs/supabase/schema.sql`: recommended tables and RLS policies.

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

There are no unit tests. Behaviour can only be verified on hardware. When you change firmware, say what you could and could not verify.

## Security rules (public repo)

* **Never commit credentials.** WiFi and AP passwords, Supabase URL and keys belong only in `secrets.h` (git-ignored) or `.env` (git-ignored).
* When adding a new credential: add a placeholder to **both** `secrets.example.h` files (if both sketches use it), then reference the macro in the `.ino` file.
* Only the Supabase **anon** key may go on a device. Never use `service_role` in firmware.
* Supabase access control lives in RLS (`docs/supabase/schema.sql`). If the firmware starts writing a new table or column, update `schema.sql` in the same PR.
* Don't print secrets to Serial.

## Conventions

* Match the existing style: Arduino C++, `const` pin and tuning constants at the top of the sketch, helper functions below `loop()`, short inline comments.
* Keep `loop()` non-blocking where possible. Use the `millis()` pattern, as `sendDataToSupabase` scheduling does. Avoid adding new `delay()` calls in the rover's main loop.
* Pin changes must update the pin map in `docs/ARCHITECTURE.md`.
* Payload or schema changes must update the data model in `docs/ARCHITECTURE.md` and `docs/supabase/schema.sql`.
* User-facing behaviour changes go in `CHANGELOG.md` under `Unreleased`.

## Git workflow

* `main` is protected. Work on a branch, open a PR, and get one review from the other team member.
* Branch names: `feat/...`, `fix/...`, `docs/...`, `chore/...`, `ci/...`.
* Commits use Conventional Commits: `feat(rover): ...`, `fix(cam): ...`, `docs: ...`, `ci: ...`. Scopes are `rover`, `cam`, `db`, `docs`, `ci`.
* Keep PRs to one concern. Fill in the PR template, including the hardware-test section.
