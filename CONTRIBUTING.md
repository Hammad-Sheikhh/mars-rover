# Contributing

## First-time setup

1. Clone the repo.
   ```sh
   git clone https://github.com/Hammad-Sheikhh/mars-rover.git
   ```
2. Install Arduino IDE 2.x (or `arduino-cli`) and the **ESP32 core 3.x** board package. The board manager URL is
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
3. Install the libraries: `Adafruit BMP280 Library`, `Adafruit Unified Sensor`, `DHT sensor library`, `MPU6050_tockn`.
4. Create your local credentials. They are git-ignored, so each of you keeps your own copy.
   ```sh
   cp rover1/secrets.example.h rover1/secrets.h
   cp cam1/secrets.example.h  cam1/secrets.h
   ```
   Ask the project owner for the Supabase URL and anon key over a private channel. **Never paste them in issues, PRs or commits.**
5. Set up the Earth Station (Python 3.11+). One command creates `.venv/`, installs everything and creates `.env`:
   ```sh
   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1   # Windows
   sh scripts/setup.sh                                          # macOS / Linux
   ```
   Then check it works: `python -m earth_station --sim` and `pytest`.

## Workflow

1. Sync `main`, then branch from it.
   ```sh
   git switch main && git pull
   git switch -c feat/short-description
   ```
2. Make small, focused commits using [Conventional Commits](https://www.conventionalcommits.org/):
   ```
   feat(rover): add left-turn fallback when right side is blocked
   fix(cam): drop x-upsert header on image upload
   docs: update pin map for new IR sensor
   ```
   Scopes: `rover`, `cam`, `station`, `db`, `docs`, `ci`.
3. Push and open a pull request into `main`. Fill in the template.
4. CI must pass: both sketches compile, the secret scan is clean, and the Earth Station sets up, lints and tests cleanly on Windows, macOS and Linux.
5. The other team member reviews. Squash-merge once it's approved.

## Rules of thumb

* **One concern per PR.** A firmware change and a refactor go in separate PRs.
* **Test on hardware** before asking for review, and say in the PR what you tested and what you couldn't.
* **Keep docs in sync.**
  * Pins changed: update `docs/ARCHITECTURE.md`.
  * Payload or table changed: update `docs/ARCHITECTURE.md` and `docs/supabase/schema.sql`.
  * Behaviour changed: add a line to `CHANGELOG.md` under `Unreleased`.
* **New credential?** Add a placeholder to `secrets.example.h`, never a real value.

## If you accidentally commit a secret

Don't just delete it in a new commit, because it stays in the history. Tell the project owner straight away, then:

1. Rotate the credential: change the WiFi password, or regenerate the Supabase key.
2. Follow [SECURITY.md](SECURITY.md).
