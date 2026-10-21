# Mars Rover: project spec

This is the plan for the whole project: what we're building, how it should behave, how anyone sets it up, and the order we build it in. If the plan changes, we change this file first.

* **What already works, and how:** [README.md](README.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/EARTH_STATION.md](docs/EARTH_STATION.md)
* **What we did each session:** [PROGRESS.md](PROGRESS.md)
* **This file:** where we're going.

Last updated: 2026-10-21.

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
| **Project leader** (repo owner) | Laptop, rover and camera (since 2026-10-20) | Earth Station, mission control page, photo descriptions, Jev connection, firmware changes, and hardware tests in person. |
| **Teammate** | No rover for now | Review and advice; does not flash firmware for now. |

**Every laptop-side feature must still work against the simulator first.** Firmware changes are written and compile-checked by CI, then flashed and tested on the real boards by the leader. The rover and camera are **two separate boards**: each has its own firmware, and each needs its own flash. Flashing `rover1` does not update `cam1`, and vice versa.

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
| E3 | Safety gate rules stay as they are, except the deliberate additions in E5. Changing them needs a test that shows the new behaviour. |
| E4 | `Ctrl+C`, the STOP button, or any crash ends with a `stop` sent to the rover. |
| E5 | **Keep a real gap and get unstuck (2026-10-22).** Forward is refused when the ultrasonic reads less than `SAFE_DISTANCE_CM` (45 cm) — the firmware's own veto is 20 cm, which is too late; a negative distance means "no echo within ~2 m" and stays drivable. `reverse` is allowed below `MIN_CONFIDENCE` when something is closer than the safe distance. When forward is refused with no room, the station reverses once, measures again, and if the gap did not improve pivots three 500 ms steps (~90°) toward the open side; after three tries without room it stops and asks for a hand. Every step waits for the move to finish before the next is sent. |

### 4.4 Mission control page

| # | Requirement |
|---|---|
| M1 | The Earth Station serves a page at `http://127.0.0.1:8000` (the laptop's own address; `MISSION_CONTROL_PORT` changes the number). It opens in the browser when the program starts. Nothing extra to install. |
| M2 | It shows: the latest camera photo and its description, live sensor readings, the rover's mode, Jev's last choice with its confidence, what the safety gate did, and whether each link (rover, camera, Jev, vision) is OK. |
| M3 | A big **STOP** button sends `stop` to the rover and pauses Jev until you press **Resume**. |
| M4 | It works the same in `--sim` mode, so it can be built and demoed with no hardware. |
| M5 | It's only reachable from the laptop itself (`localhost`), not from other devices on the hotspot. |

### 4.5 Photo descriptions (`describe.py`)

| # | Requirement |
|---|---|
| D1 | A vision AI turns each camera photo into the short description Jev reads: `summary`, `obstacle_ahead`, `clear_side`, `hazards`. That shape is defined and checked in `describe.py`. |
| D2 | `VISION_PROVIDER=gemini` uses a Google AI Studio key; `anthropic` keeps the older Claude path. `VISION_MODEL` defaults to `gemini-3.5-flash`, and `VISION_FOCUS` names the objects that matter. The reply is enforced in a fixed JSON shape. |
| D3 | Target **2–5 s** per description; `VISION_TIMEOUT_S` (default 40 s) is the hard limit. If it is slower or fails, the scene goes stale and the safety gate stops the rover. |
| D4 | Test it on saved photos with no rover: `python -m earth_station.describe photo.jpg`. Keep a few sample photos in `tests/photos/` for the tests. |
| D5 | **Live vision is optional.** `DESCRIBE_MODE=mock` stays the safe default without a key. The free Gemini tier is **20 requests/day per model** (measured 20 Oct 2026), so live vision must be budgeted (D6). A real photo in `mock` mode must tell Jev honestly that there is no camera vision, and never claim the way is clear. |
| D6 | **Cost guard (2026-10-21):** one description is reused for many Jev decisions. Refresh only when needed: the first frame, the rover has moved `VISION_REFRESH_MOVES` (14) steps, the description is older than `VISION_REFRESH_MS` (12 s), something within `VISION_CLOSE_CM` (60 cm) is 20 cm closer, or Jev was unsure. Hard forward limits: `SCENE_MAX_AGE_MS` (20 s) and `SCENE_MAX_MOVES` (24); turns and reverse stay allowed. A run makes at most `VISION_MAX_CALLS` live descriptions (default **6**, pre-flight included). If no description succeeds for `VISION_LOST_STOP_S` (default 60 s), or the budget is spent and the view is stale, the run stops cleanly instead of waiting forever. |
| D7 | **The prompt knows the rover (2026-10-22).** It states the rover is about 15 cm wide and 20 cm tall, that a gap about 25 cm or wider is passable, and that floor visible under or around an object means the way is open. "Blocked within 1 m" made every passable gap look like a wall, and Jev then refused to move. |

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
| R7 | **Firmware 2.6.0 (next flash):** ignore accelerometer samples whose magnitude is far from 1 g, so one wheel bump cannot stamp a `Tilt Warning` (the station now hides stale warnings, but the firmware should not create them). |
| R8 | **Firmware 2.6.0:** the web server must survive the station's request rate. On 22 Oct it stopped answering HTTP for the rest of a run after ~18 s at ~4.2 requests/s (telemetry every 0.5 s plus a command every ~0.45 s) while still answering ping; the watchdog stopped the wheels. Until then the station polls telemetry every 1000 ms. |

The camera needs only N3, N4 and N5. Its `/capture` endpoint already does what we need.

## 5. Setup procedure (the target)

This is how setup looks today, with milestones 1–10 done. The README always shows the steps that work *today*.

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
4. Flash both boards from the Arduino IDE (the steps are in the README). **Each board is a separate flash: `rover1` and `cam1`; one upload does not update the other.** Then open the Serial monitor. Each board should print "WiFi connected" and its `.local` name.
5. Connect the laptop to the same hotspot.
6. Run `python -m earth_station --check`. All lines should say OK.

If the person who flashes the rover isn't the person who runs the Earth Station, send the token to the other person **privately** (not in GitHub). Both `.env` and `rover1/secrets.h` must have the same value.

### C. Every time you drive

1. Turn on the hotspot, power the rover (keep it still for 3 seconds while the gyro calibrates), connect the laptop.
2. `python -m earth_station --suggest`. Watch what Jev *would* do.
3. On the rover's control page, press **Jev Auto**.
4. When you trust it: stop, then run `python -m earth_station` to let Jev drive. Stay close, in an open space.

## 6. Milestones (the build order)

Each milestone is **one pull request**. Laptop work is tested on the simulator first; hardware tests are done by the leader in person.

| # | Milestone | Needs hardware? | Done when |
|---|---|---|---|
| 0 | **This spec** | No | Merged. |
| 1 | **Easy setup**: `WIFI_SSID`/`WIFI_PASS` in `.env`, the `earth_station.secrets` helper with token generation, the `--check` command, README Quick Start rewritten. ✅ Done (PR #8). | No | A fresh clone on another laptop goes from zero to `--sim` by following the README alone. |
| 2 | **Find the boards**: `.local` lookup plus a network scan, using `GET /id`. The simulator answers `/id` too. ✅ Done (PR #9). | No | Tests prove the finder works against the simulator, and `--check` reports what it found. |
| 3 | **Rover firmware: Jev Auto** (R1–R6). ✅ Done: hardware checklist passed on the real rover 19–20 Oct (PR #7). | Hardware test (done) | CI compiles it, and the hardware checklist passes on the real rover. |
| 4 | **Camera firmware**: `cam.local`, `/id`, boot messages. ✅ Done: hardware checklist passed on the real camera 19–20 Oct (PR #10). | Hardware test (done) | Same as 3. |
| 5 | **Photo descriptions**: live `describe.py`, Gemini by default. ✅ Done and live-tested; free tier measured at 20 requests/day per model. | No (saved photos) | Sample photos give sensible descriptions, and tests pass with the vision AI mocked. |
| 6 | **Mission control page.** ✅ Done: works on the simulator, with tests for STOP/Resume, plus a plain-word, step-by-step view of each decision and a recent-decisions table. | No | Usable in `--sim`, the STOP button works, and there are tests for STOP/Resume. |
| 7 | **Live Jev.** ✅ Done: spending guard (J4) plus 30-call and 200-call runs on the real rover, 20 Oct. | No (needs credits) | `--sim --live-jev` runs with the real Jev and stays within `JEV_MAX_CALLS`. |
| 8 | **First real drive.** ✅ Done 20 Oct: 30-call and 200-call live-Jev + Gemini runs. The 200-call run exposed the vision cost/quota limit and a hang when vision disappears. | Yes (done) | Section 5 B and C work end to end, and the run log is saved and reviewed together. |
| 9 | **Vision cost control**: reuse descriptions, refresh on demand, `VISION_MAX_CALLS` budget (target 6), clean stop after 60 s without vision. ✅ Done 21 Oct (PR #33): the 200-decision simulator run used exactly 6 live descriptions in the worst case (a new photo wanted after every move); rate limits and a spent budget stop the run cleanly. | No | A 200-call run uses **≤6** live descriptions; the station stops cleanly on 429/503 instead of waiting; simulator tests cover the budget and the clean stop. |
| 10 | **Drive tuning on the real rover** (E5, D7): the honest tilt brief, the 45 cm forward floor, unsure-reverse, the reverse → measure → pivot unstick manoeuvre, the size-aware vision prompt, and the station's share of the request-rate problem. ✅ Done 22 Oct (branch `fix/station-drive-tuning`): the phantom `Tilt Warning` was in 164 of 171 briefs and cost 90 of 196 forwards; after the fix confidence was 0.82–0.97 with 33 forwards in a row, 159 tests pass. | Yes (partly) | A real run no longer rocks between forward and reverse, keeps 45 cm from furniture, and pivots out of a dead end instead of pushing. |
| 11 | **Firmware 2.6.0** (R7, R8): accelerometer spike rejection and a web server that survives the station's request rate. | Yes (flash) | A 5-minute drive with telemetry every 0.5 s keeps answering `/sensors/data`, and a bump during a drive never produces a `Tilt Warning`. |
| 12 | **Acceptance drive with vision**: one live-vision run in an open stretch, recording how far the rover gets per description and confirming the unstick manoeuvre in the log. | Yes (vision quota) | The run log shows forward moves per vision call, a clean end at the budget, and at most one unstick manoeuvre. |

**Live Jev (7) came first**, because it's the heart of the project (decided 2026-10-05). Milestones 1–10 are done. **Next: milestone 11 (firmware 2.6.0, needs a flash), then milestone 12 (the acceptance drive with live vision).** Jev's official docs are at [docs.typesafe.ai](https://docs.typesafe.ai).

## 7. Not in scope (for now)

* **Supabase** stays as it is and will be removed later. No new work on it.
* No cloud hosting, no website, no phone app.
* Jev doesn't see photos directly. It only reads the description.
* No driving from outside the hotspot (over the internet).

## 8. Open questions

| Question | How we'll answer it |
|---|---|
| Does `.local` work on our phone's hotspot? Some phones block devices from seeing each other. | Works on the current hotspot; the network scan is the backup. Windows sometimes rejoins the home WiFi, so pin the hotspot before trusting a "board not found" result. |
| What is the cheapest safe vision cadence? | Answered by milestone 9: one description is reused until the rover moves 14 steps or 12 s pass (or something close gets closer, or Jev is unsure), with a hard cap of 6 descriptions per run and a clean stop when vision is gone. Milestone 12 measures how far the rover actually gets per description. |
| Why does the rover's web server stall under load? | Seen on 22 Oct: after ~18 s at ~4.2 requests/s it answered ping but no HTTP. Milestone 11 fixes it in the firmware; until then the station polls telemetry every 1000 ms. |
| Can Jev accept the photo directly? | Ask TypeSafe. If Jev can see images, the separate vision bill disappears. Until then, `describe.py` stays. |
| A free/local way for the camera to help (no paid API) | Later: a small vision model on the laptop (for example Ollama) or simple image rules. The vision budget in milestone 9 is the cheaper first step. |

## 9. How we work

1. **Pick the next milestone** from section 6 and ask Claude to build it. Claude explains each step as it goes (see `CLAUDE.md`).
2. Claude works on a **branch**, for example `feat/easy-setup`, never directly on `main`.
3. Try it yourself: `python -m earth_station --sim`, and the tests (`pytest`).
4. Claude **commits**, **pushes** and opens a **pull request** (PR) on GitHub. CI runs the automatic checks. Wait for green ticks.
5. **Firmware PRs:** the teammate flashes the branch, follows the hardware checklist in the PR, and comments with the results.
6. You **merge** the PR on GitHub, then run `git switch main` and `git pull` on your laptop.
7. At the end of a session, Claude updates `PROGRESS.md`, and this spec if the plan changed.
