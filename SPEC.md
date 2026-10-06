# Mars Rover: project spec

This is the plan for the whole project: what we're building, how it should behave, how anyone sets it up, and the order we build it in. If the plan changes, we change this file first.

* **What already works, and how:** [README.md](README.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/EARTH_STATION.md](docs/EARTH_STATION.md)
* **What we did each session:** [PROGRESS.md](PROGRESS.md)
* **This file:** where we're going.

Last updated: 2026-10-05.

---

## 1. The goal in one paragraph

A small rover drives around a room by itself. An AI called **Jev** chooses each move. Jev doesn't run on the rover. It runs online, and a laptop program called the **Earth Station** talks to it. The rover, the camera and the laptop all join **one phone hotspot**. About twice a second the laptop reads the rover's sensors and the camera's latest photo, asks Jev "what next?", checks the answer for safety, and tells the rover to move. You watch everything on a **mission control page** in the laptop's browser, and you can press **STOP** at any time.

```
                      Phone hotspot (one WiFi for everything)
   ┌────────────────────────────────────────────────────────────────┐
   │                                                                │
   │   Rover (ESP32)  rover.local      Camera (ESP32-CAM)  cam.local│
   │      ▲   │ sensors                    │ photos                 │
   │ moves│   ▼                            ▼                        │
   │   ┌──────────────── Laptop: Earth Station ─────────────────┐   │
   │   │ reads sensors + photo → describes photo → asks Jev →   │   │
   │   │ safety gate → sends move → logs it → mission control   │   │
   │   └──────────────────────────┬─────────────────────────────┘   │
   └──────────────────────────────┼─────────────────────────────────┘
                                  │ internet (through the hotspot)
                       Jev (choose a move) + vision AI (describe photo)
```

## 2. Words you'll see (glossary)

| Word | Meaning |
|---|---|
| **ESP32** | A small, cheap computer chip with WiFi. The rover's "brain". |
| **ESP32-CAM** | An ESP32 with a camera attached. A separate board on the rover. |
| **Firmware** | The program that runs on a board (`rover1.ino`, `cam1.ino`). |
| **Flash / upload** | Copy firmware onto a board over USB, using the Arduino IDE. |
| **Serial monitor** | A window in the Arduino IDE that shows the text a board prints. Useful for seeing what it's doing. |
| **Hotspot** | Your phone acting as a WiFi router. |
| **AP (access point)** | A board making its *own* small WiFi network, so a phone can connect to it directly. Both boards already do this, for manual control. |
| **IP address** | A device's number on a network, like `192.168.43.17`. It can change each time a device connects. |
| **mDNS / `.local` name** | A way for a device to announce a name (`rover.local`), so you don't need to know its IP address. |
| **Endpoint** | One "door" on a board's web server, like `/sensors/data`. The laptop knocks on these doors. |
| **Telemetry** | Sensor readings sent from the rover (distance, tilt, temperature, …). |
| **Token** | A shared password between laptop and rover, so only *your* laptop can drive it. |
| **Watchdog** | A timer on the rover: if no command arrives for 1.5 s, stop. It protects against a crashed laptop or lost WiFi. |
| **Simulator (sim)** | A fake rover and camera inside the laptop program. Lets us build and test with no hardware. |
| **Mock** | A pretend version of an online service (a fake Jev, a fake vision AI), for testing without accounts or internet. |
| **`.env`** | A private settings file on the laptop. Never uploaded to GitHub. |
| **`secrets.h`** | The private settings file for each board. Never uploaded to GitHub. |
| **venv** | A private Python install inside the project folder (`.venv/`), so the project doesn't clash with anything else on the laptop. |
| **CI** | Automatic checks GitHub runs on every pull request: compile the firmware, run the tests, scan for leaked passwords. |

## 3. Who does what

| Person | Has | Does |
|---|---|---|
| **Project leader** (repo owner) | Laptop, no rover yet | Earth Station, mission control page, photo descriptions, Jev connection, and writing the firmware changes (CI compile-checks them). |
| **Teammate** | The rover and camera | Flashes firmware, runs the hardware test checklist in each firmware pull request, reports what happened. |

Because the leader has no hardware, **every laptop-side feature must work against the simulator first**. Firmware changes are written and compile-checked by the leader, then tested on the real rover by the teammate.

## 4. Requirements

### 4.1 Easy setup on any laptop

| # | Requirement |
|---|---|
| S1 | Works on Windows, macOS and Linux. The only things to install first are **Python 3.11+** and **git**. |
| S2 | **One command** sets everything up (`scripts/setup.ps1` or `scripts/setup.sh`). Running it again is safe. |
| S3 | Right after setup, `python -m earth_station --sim` works with **no rover, no internet and no keys**. |
| S4 | You type the hotspot name and password **once**, into `.env`. A helper writes both boards' `secrets.h` files from it, so the two boards can't end up on different networks. |
| S5 | The rover token is **made automatically** (a long random value) and written into both `.env` and `rover1/secrets.h`. Nobody has to invent one. |
| S6 | **You never type an IP address.** The Earth Station finds the boards by name (`rover.local`, `cam.local`). If that fails, it scans the hotspot network for them. |
| S7 | A **check command** (`python -m earth_station --check`) tests every piece and says in plain words what's wrong and how to fix it, e.g. *"Rover not found. Is it switched on and joined to the hotspot? Look for 'WiFi connected' in its Serial monitor."* |
| S8 | The README's Quick Start lists the exact steps, for both "just the laptop" and "with the real rover". |

### 4.2 Network

| # | Requirement |
|---|---|
| N1 | One **phone hotspot** is the shared WiFi. The hotspot also gives internet, which Jev, the vision AI and (for now) Supabase need. |
| N2 | Each board keeps its own AP and control page (`192.168.4.1`) for manual driving, as today. |
| N3 | The rover announces `rover.local` and the camera `cam.local` (mDNS). The Earth Station looks these up itself, so it doesn't depend on the laptop's operating system supporting `.local`. |
| N4 | Each board answers `GET /id` with `{"board": "rover"}` or `{"board": "camera"}`, plus its firmware version. That's how the network scan recognises them. |
| N5 | Each board prints, on the Serial monitor at boot: hotspot joined yes/no, its IP address and its `.local` name. Never passwords. |

### 4.3 Earth Station behaviour

Already built (see [docs/EARTH_STATION.md](docs/EARTH_STATION.md)): the decide loop, the safety gate, run logs, the simulator, a mock Jev and `--suggest` mode. It keeps working as it does today.

| # | Requirement |
|---|---|
| E1 | Three ways to run: `--sim` (all fake), `--suggest` (real boards, Jev decides but the rover never moves), normal (Jev drives). |
| E2 | It only drives while the rover says `mode: "jev"`. Any button on the phone control page takes the rover out of Jev Auto. |
| E3 | Safety gate rules stay as they are. Changing them needs a test that shows the new behaviour. |
| E4 | `Ctrl+C`, the STOP button, or any crash ends with a `stop` sent to the rover. |

### 4.4 Mission control page

| # | Requirement |
|---|---|
| M1 | The Earth Station serves a page at `http://localhost:8000`. It opens in the browser when the program starts. Nothing extra to install. |
| M2 | It shows: the latest camera photo and its description, live sensor readings, the rover's mode, Jev's last choice with its confidence, what the safety gate did, and whether each link (rover, camera, Jev, vision) is OK. |
| M3 | A big **STOP** button sends `stop` to the rover and pauses Jev until you press **Resume**. |
| M4 | It works the same in `--sim` mode, so it can be built and demoed with no hardware. |
| M5 | It's only reachable from the laptop itself (`localhost`), not from other devices on the hotspot. |

### 4.5 Photo descriptions (`describe.py`)

| # | Requirement |
|---|---|
| D1 | A vision AI (Claude) turns each camera photo into the short description Jev reads: `summary`, `obstacle_ahead`, `clear_side`, `hazards`. That shape is already defined and checked in `describe.py`. |
| D2 | Key in `.env` (`VISION_API_KEY`, an Anthropic key). The model (`VISION_MODEL`, default `claude-opus-5-5`) and how hard it thinks (`VISION_EFFORT`, default `low`) are settings too. Claude answers in a fixed JSON shape (structured output), so the reply always has the four fields. |
| D3 | It must answer within about 1.5 s. If it's slow or fails, the scene goes stale, and the safety gate already stops the rover then. |
| D4 | Test it on saved photos with no rover: `python -m earth_station.describe photo.jpg`. Keep a few sample photos in `tests/photos/` for the tests. |
| D5 | **Live vision is optional and off by default** (decided 2026-10-06: the Claude API costs money we don't have now). Without it, Jev drives on the sensors only. A real photo in `mock` mode must then tell Jev honestly that there is no camera vision, and never claim the way is clear. |

### 4.6 Jev

| # | Requirement |
|---|---|
| J1 | `JEV_MODE=mock` stays the default. `live` uses the real Jev API with `JEV_API_URL` and `JEV_API_KEY` from `.env`. |
| J2 | Jev picks one of `forward`, `turn_left`, `turn_right`, `reverse`, `stop`, with a confidence. |
| J3 | The request format follows TypeSafe's own [API reference](https://docs.typesafe.ai/api) (checked 2026-10-06). |
| J4 | **Spending guard** (2026-10-06): `--sim` uses the pretend Jev unless `--live-jev` is given; each run makes at most `JEV_MAX_CALLS` live calls (default 20), then stops the rover and ends; the run prints the calls and tokens used. Tests never call the real Jev. |

### 4.7 Rover firmware (Jev Auto)

The full contract is in [docs/EARTH_STATION.md → Rover protocol](docs/EARTH_STATION.md#rover-protocol). In short:

| # | Requirement |
|---|---|
| R1 | A third **Jev Auto** button on the rover's control page, next to Start/Stop and Autonomous. |
| R2 | `/sensors/data` adds `mode` and `distance_cm`. |
| R3 | `POST /jev/cmd` with the token: runs one short move, or refuses with a reason (not in Jev mode, obstacle, tilt, bad token). |
| R4 | Watchdog: in Jev Auto, no command for 1.5 s means stop. |
| R5 | No `delay()` in the Jev Auto path. Moves are timed with `millis()`, so the rover keeps answering. |
| R6 | `rover.local` name and `GET /id` (N3, N4). |

The camera needs only N3, N4 and N5. Its `/capture` endpoint already does what we need.

## 5. Setup procedure (the target)

This is how setup will look when milestones 1–3 are done. The README always shows the steps that work *today*.

### A. Any laptop, once (no hardware needed)

1. Install **Python 3.11+** (python.org; on Windows tick "Add Python to PATH") and **git** (git-scm.com).
2. Get the project:
   ```sh
   git clone https://github.com/Hammad-Sheikhh/mars-rover.git
   cd mars-rover
   ```
3. Run setup:
   * Windows: `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1`
   * Mac / Linux: `sh scripts/setup.sh`
4. Try it: `python -m earth_station --sim`. Mission control opens in your browser, and a fake rover drives around.

### B. Connect the real boards, once per hotspot

1. On your phone, turn on the hotspot. Use the 2.4 GHz band if your phone asks, because ESP32 boards can't see 5 GHz WiFi.
2. On the laptop, put the hotspot name and password in `.env` (`WIFI_SSID`, `WIFI_PASS`).
3. Run `python -m earth_station.secrets`. It creates `rover1/secrets.h` and `cam1/secrets.h` with the same hotspot details, and creates the rover token.
4. Flash both boards from the Arduino IDE (the steps are in the README). Then open the Serial monitor. Each board should print "WiFi connected" and its `.local` name.
5. Connect the laptop to the same hotspot.
6. Run `python -m earth_station --check`. All lines should say OK.

If the person who flashes the rover isn't the person who runs the Earth Station, send the token to the other person **privately** (not in GitHub). Both `.env` and `rover1/secrets.h` must have the same value.

### C. Every time you drive

1. Turn on the hotspot, power the rover (keep it still for 3 seconds while the gyro calibrates), connect the laptop.
2. `python -m earth_station --suggest`. Watch what Jev *would* do.
3. On the rover's control page, press **Jev Auto**.
4. When you trust it: stop, then run `python -m earth_station` to let Jev drive. Stay close, in an open space.

## 6. Milestones (the build order)

Each milestone is **one pull request**. Laptop work comes first, because the leader has no rover.

| # | Milestone | Needs hardware? | Done when |
|---|---|---|---|
| 0 | **This spec** | No | Merged. |
| 1 | **Easy setup**: `WIFI_SSID`/`WIFI_PASS` in `.env`, the `earth_station.secrets` helper with token generation, the `--check` command, README Quick Start rewritten. ✅ Done (PR #8). | No | A fresh clone on another laptop goes from zero to `--sim` by following the README alone. |
| 2 | **Find the boards**: `.local` lookup plus a network scan, using `GET /id`. The simulator answers `/id` too. ✅ Done (PR #9). | No | Tests prove the finder works against the simulator, and `--check` reports what it found. |
| 3 | **Rover firmware: Jev Auto** (R1–R6). 🧪 Written; waiting for the hardware test. | Teammate tests | CI compiles it, and the teammate completes the hardware checklist in the PR. |
| 4 | **Camera firmware**: `cam.local`, `/id`, boot messages. 🧪 Written (firmware 2.1); waiting for the hardware test. | Teammate tests | Same as 3. |
| 5 | **Photo descriptions**: live `describe.py` using Claude vision. ✅ Code done, tested with a fake Claude. ⏸ Using it is paused: the API costs money, so we drive on sensors only for now (D5). | No (saved photos) | Sample photos give sensible descriptions, and tests pass with the vision AI mocked. |
| 6 | **Mission control page.** | No | Usable in `--sim`, the STOP button works, and there are tests for STOP/Resume. |
| 7 | **Live Jev.** ✅ Code done, with a spending guard (J4). Credits bought; first live test next. | No (needs credits) | `--sim --live-jev` runs with the real Jev and stays within `JEV_MAX_CALLS`. |
| 8 | **First real drive.** | Yes | Section 5 B and C work end to end, and the run log is saved and reviewed together. |

**Live Jev (7) comes first**, because it's the heart of the project (decided 2026-10-05). Jev's official docs are at [docs.typesafe.ai](https://docs.typesafe.ai). After that, milestones 1, 2, 5 and 6 can be done in any order. Milestone 3 is the one the teammate is waiting for, so it's worth doing early.

## 7. Not in scope (for now)

* **Supabase** stays as it is and will be removed later. No new work on it.
* No cloud hosting, no website, no phone app.
* Jev doesn't see photos directly. It only reads the description.
* No driving from outside the hotspot (over the internet).

## 8. Open questions

| Question | How we'll answer it |
|---|---|
| Does `.local` work on our phone's hotspot? Some phones block devices from seeing each other. | Milestone 8. The network scan is the backup. If the phone blocks devices completely, use a different phone or a small travel router. |
| A free way for the camera to help (no paid API) | Later, after the first real drive. Options: a small vision AI running on the laptop (for example with Ollama), or simple image rules such as "is the bottom of the photo mostly floor?". Measure speed on the teammate's sample photos. |
| Is one description every 1.5 s fast enough to avoid obstacles? | The rover's own 20 cm forward veto covers us meanwhile. Measure it in milestone 8. |

## 9. How we work

1. **Pick the next milestone** from section 6 and ask Claude to build it. Claude explains each step as it goes (see `CLAUDE.md`).
2. Claude works on a **branch**, for example `feat/easy-setup`, never directly on `main`.
3. Try it yourself: `python -m earth_station --sim`, and the tests (`pytest`).
4. Claude **commits**, **pushes** and opens a **pull request** (PR) on GitHub. CI runs the automatic checks. Wait for green ticks.
5. **Firmware PRs:** the teammate flashes the branch, follows the hardware checklist in the PR, and comments with the results.
6. You **merge** the PR on GitHub, then run `git switch main` and `git pull` on your laptop.
7. At the end of a session, Claude updates `PROGRESS.md`, and this spec if the plan changed.
