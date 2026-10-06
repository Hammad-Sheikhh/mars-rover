# Project progress

The project diary: what we did, what we decided, and what's next. Claude reads it at the start of every session (it's imported in `CLAUDE.md`) and adds to it at the end of every session.

**Rules for this file**
- Newest session at the top of the session log.
- Plain words, written for a beginner.
- Never write passwords, keys or WiFi names here. This repo is public.

---

## Where we are now

| Part | Status |
|---|---|
| Rover (ESP32): driving, sensors, own WiFi control page | ✅ Works |
| Camera (ESP32-CAM): photos, own WiFi live view | ✅ Works |
| Supabase (online database for readings and photos) | ✅ Works, but **will be dropped later** |
| Earth Station (laptop program that lets Jev drive) | 🧪 Works with the fake rover; the real rover can't talk to it yet |
| Project plan (`SPEC.md`) | ✅ Written. Milestones 0–8 |
| Easy setup: hotspot typed once in `.env`, `--check` | ✅ Milestone 1 merged (PR #8) |
| Finding the boards automatically | ✅ Milestone 2 merged (PR #9). Tested on the simulator |
| Camera name `cam.local` and `/id` | 🧪 Milestone 4 merged (camera firmware 2.1, PR #10). Waiting for the teammate's hardware test |
| Rover code for "Jev Auto" mode | 🧪 Milestone 3: written (firmware 2.1, PR #7). Waiting for the teammate's hardware test |
| Photo descriptions with Claude vision (`earth_station/describe.py`) | ⏸ Milestone 5 merged (PR #12) and tested with a fake Claude. Switched off for now: the API costs money, so we drive on sensors only |
| Mission control page in the browser, with STOP | ✅ Milestone 6 (PR #17). Works on the simulator |
| Real Jev connection | ✅ Key works (first real call: 571 ms). Spending guard merged (PR #15) |

**Who has what:** the teammate has the physical rover and camera. The project leader (repo owner) works on the laptop side.

## Decisions so far

- **Jev drives through a laptop (the "Earth Station")** on the same WiFi as the rover and camera. We chose this over cloud setups. *Why:* it's simplest, the fastest to react, and keeps keys off the rover.
- **No Vercel website.** Dropped on 2026-10-04.
- **Supabase will be removed** when the architecture changes later. So we don't rotate its key or invest more in it.
- **n8n and the old web dashboard were removed.** They weren't working.
- **The repo is public.** Passwords and keys live only in files that never go to GitHub: `.env`, `rover1/secrets.h` and `cam1/secrets.h`.
- **The leader merges their own pull requests.** A teammate review is welcome but not required.
- **One phone hotspot** is the shared WiFi for rover, camera and laptop (2026-10-05). *Why:* it goes everywhere and works the same with any laptop.
- **Boards are found by name** (`rover.local`, `cam.local`), with a network scan as backup. *Why:* nobody has to look up or type IP addresses.
- **A mission control page** in the laptop's browser, with a big STOP button, alongside the terminal output.
- **The leader builds the photo descriptions** with Claude vision, instead of the teammate. *Why:* it needs no hardware, and the teammate can focus on testing on the rover.
- **`.env` is the one place for board settings** (2026-10-05). `python -m earth_station.secrets` writes both `secrets.h` files from it. *Why:* the two boards can never end up on different networks, and nobody has to invent a token.
- **Board addresses in `.env` are optional** (2026-10-06). Empty means "find it": `.env`, then a simulator on this laptop, then `rover.local` / `cam.local`, then a scan of the hotspot. *Why:* nobody has to look up an IP address, and the same `.env` works on any hotspot.
- **Photo descriptions use `claude-opus-5-5` at effort `low`** (2026-10-06), with a fixed answer form (structured output). Both are settings in `.env` (`VISION_MODEL`, `VISION_EFFORT`). *Why:* low effort keeps each answer quick and cheap.
- **No paid photo descriptions for now** (2026-10-06). The Claude API costs roughly $15–25 per hour of driving on the default model, which we can't afford now. `DESCRIBE_MODE` stays `mock`, and Jev drives on the distance and tilt sensors. *Why:* the rover's own safety rules already stop it before it hits things. A free option (a vision AI running on the laptop, or simple image rules) can come later. Jev's $5 is affordable and will come later.
- **Jev spending guard** (2026-10-06): each run makes at most `JEV_MAX_CALLS` real Jev calls (default 20), then stops the rover and ends. `--sim` uses the pretend Jev unless you add `--live-jev`. Tests never call the real Jev. *Why:* credits cost money, and the leader wants very careful use while we build.
- **`SPEC.md` is the plan.** Each pull request is one milestone from it.
- **The leader's manual tasks aren't written here until they're confirmed done** (2026-10-06). Claude keeps the open ones in its private memory and asks about them every session (see `CLAUDE.md`). *Why:* the diary should only say what really happened.
- **Claude explains every step and every GitHub action in beginner-friendly words** (see `CLAUDE.md`).

## Next steps

The full build order is in `SPEC.md` section 6.

1. Merge PR #17 (mission control) once its checks pass, and try it: `python -m earth_station --sim`, then press STOP and Resume in the browser.
2. One short real Jev drive on the simulator: `python -m earth_station --sim --live-jev` with `JEV_MAX_CALLS=10`, to see if Jev's choices make sense. About 10 calls.
3. Teammate: flash rover firmware 2.1 (with the new `rover1/secrets.h`) and camera firmware 2.1, and run the hardware checklists in PR #7 and PR #10. Then `python -m earth_station --check` on the hotspot should say `rover found at ... (rover.local)` and `camera found at ... (cam.local)`.
4. Teammate: save a few photos from the camera (`http://<camera address>/capture` in a browser, then save the image), for example open floor, a chair leg up close, a wall, and a dark corner. Send them to the leader. They're for trying a free way to describe photos later.
5. Milestone 8 (the first real drive) once the teammate's hardware tests pass. Until then, a free way for the camera to help (`SPEC.md` open questions) is the next laptop-only job.

---

## Session log

### 2026-10-07 — Session 8: mission control (milestone 6)

**What we did**
1. **Found PRs #15 and #16 merged**, and the TypeSafe skill installed.
2. **Built the mission control page** (`earth_station/mission_control.py` and `mission_control.html`). Every run opens `http://127.0.0.1:8000` in the browser. It shows:
   - the photo and its description;
   - the sensor readings and the rover's mode;
   - Jev's last choice, with the chance it gave each move;
   - what the safety gate did, and what the rover answered;
   - whether the rover, camera, vision and Jev links are OK.
3. **STOP button** (or the `Esc` key): stops the rover at once and pauses Jev. An answer Jev was still working on is thrown away. **Resume** lets Jev drive again.
4. **Only this laptop can use it.** Phones on the hotspot can't open it, and other websites in the browser can't press its buttons.
5. **6 new tests** (90 in total). We also tried it by hand on the simulator: STOP gave 0 moves in 2 seconds, Resume 4 moves in 2 seconds.
6. New flag `--no-browser` and setting `MISSION_CONTROL_PORT` (default 8000). Opened **PR #17**.

**Things to remember**
- The simulator's photos are pretend, so the page shows "this photo can't be shown" plus the description. Real camera photos will show as pictures.
- `Ctrl+C` in the terminal still works as a second STOP.

### 2026-10-06 — Session 7: the real Jev, carefully

**What we did**
1. **The leader bought Jev credits** and saved the key in `.env`. We checked it was saved without ever showing it on screen.
2. **Checked our Jev code against TypeSafe's live docs.** It matches: same address, question format and answer fields. Each answer also says how many tokens it used, which is what TypeSafe charges for.
3. **Built a spending guard** (PR #15, all 6 CI checks passed, not merged yet):
   - `JEV_MAX_CALLS` (default 20): the most real Jev calls in one run. Then the station stops the rover, ends by itself and prints the calls and tokens used.
   - `--sim` is always free (pretend Jev). Only the new `--live-jev` flag spends credits.
   - 9 new tests, all with a fake Jev (84 in total).
4. **First real Jev call:** `python -m earth_station --check --sim --live-jev` gave "Jev answering, 571 ms". That was exactly 1 call.
5. **Started installing TypeSafe's skill** for Claude Code: the collection (marketplace) is added, the plugin isn't installed yet. See "Next steps" step 1.
6. **New rule in `CLAUDE.md`** (PR #16): Claude explains every task that is on the leader in full: what, why, where, numbered steps, what you should see, and the cost.

**Things to remember**
- `.env` still says `JEV_MODE=mock`, so normal runs are free. `--live-jev` is the switch for the real Jev.
- In the Claude Code window, right-click **pastes**, and the ↑ key repeats the last command. Type commands fresh.

### 2026-10-06 — Session 6: photo descriptions (milestone 5)

**What we did**
1. **Claude now describes the camera photos** (`earth_station/describe.py`). With `DESCRIBE_MODE=live` and an Anthropic key in `VISION_API_KEY`, each photo goes to Claude. Claude fills in a fixed form: what's ahead, whether it's blocked, which side is clear, and any hazards. `mock` is still the default, so nothing changes without a key.
2. **New settings:** `VISION_MODEL` (default `claude-opus-5-5`), `VISION_EFFORT` (default `low`) and `VISION_TIMEOUT_S` (default 10 seconds).
3. **Problems never crash the station.** A wrong key, no internet, a refusal or a bad answer becomes a clear message. Then the safety gate stops the rover, because the scene gets too old.
4. **`python -m earth_station.describe a.jpg b.jpg`** describes saved photos and prints how long each one took.
5. **14 new tests** with a fake Claude (71 in total). Updated the README (new Quick Start part D; Supabase is now part E), `.env.example`, `SPEC.md`, `docs/EARTH_STATION.md` and `CHANGELOG.md`.
6. All 6 CI checks passed. **Merged PR #12.**

7. **Decided not to use the paid Claude API for now** (too expensive for us). The code stays in the project, switched off. We wrote this into `SPEC.md` (D5, and a new open question about free options).

8. **Merged PR #13** (this diary and the decision). Then a **small safety fix** (PR #14): without paid vision, a real photo now tells Jev "No camera vision. Judge what is ahead from the distance sensor only", instead of hinting that both sides are clear. 4 new tests (75 in total) show the pretend Jev still drives forward when the sensor sees open space, turns at 30 cm and backs up at 10 cm.

**Things to remember**
- Not tried with the real Claude. If we ever turn it on: the key goes only in `.env`, and we measure speed (under about 1.5 s) and cost first.
- Teammate photos are still useful: they let us try a free option later.

### 2026-10-06 — Session 5: the camera's name (milestone 4)

**What we did**
1. **Found PR #9 already merged** (all 6 CI checks green), brought the laptop's `main` up to date, and deleted the old local branch.
2. **Camera firmware 2.1** (`cam1/cam1.ino`), copying how the rover does it:
   - it announces the name `cam.local` once it has joined the hotspot;
   - `GET /id` answers `{"board": "camera", "firmware": "2.1.0"}`, so the network scan recognises it;
   - at boot the Serial monitor shows "Hotspot joined: yes/NO", the IP address, the name, the AP address and the firmware version. Never passwords.
3. **Updated the finder's help message**, `.env.example`, the README, `SPEC.md`, `docs/EARTH_STATION.md`, `docs/ARCHITECTURE.md` and `CHANGELOG.md`. You now leave `CAMERA_URL` empty too.
4. All 57 tests pass, and all 7 CI checks passed (including "Compile cam1"). **Merged PR #10.** Not tested on the real camera yet.
5. The leader confirmed the teammate is now a collaborator on GitHub.
6. **New rule in `CLAUDE.md`:** Claude doesn't write the leader's manual tasks in this diary until the leader confirms they're done. It keeps the open ones in its private memory and reminds the leader every session.

**Things to remember**
- The teammate must flash the new camera code before the finder can find the camera. Older camera code has no name and no `/id`, so `CAMERA_URL` is still needed for it.

### 2026-10-06 — Session 4: finding the boards (milestone 2)

**What we did**
1. **Merged PR #8** (milestone 1) after all 6 CI checks passed, and brought the laptop's `main` up to date.
2. **Fixed our own `.env`:** renamed the WiFi settings to `WIFI_SSID` / `WIFI_PASS` and removed the old camera WiFi lines. Then we re-ran `earth_station.secrets` (both `secrets.h` updated) and `--check` (all settings OK).
3. **Built the board finder** (`earth_station/finder.py`). For each board it tries the address in `.env`, then a simulator on this laptop, then the board's name, then a scan of the network asking every address "which board are you?" (`GET /id`).
4. **Wrote our own `.local` lookup** (`earth_station/mdns.py`), so finding `rover.local` doesn't depend on Windows, Mac or Linux supporting it.
5. **Connected the finder** to the normal run, `--check` and `earth_station.drive`. `ROVER_URL` / `CAMERA_URL` are now optional.
6. **11 new tests** (57 in total), all against the simulator, with no real network. We also tried it for real on the laptop: without boards, `--check` scanned 253 addresses in about 11 seconds and said where it had looked. With the simulator running, it found the fake boards with nothing typed.
7. Fixed `CHANGELOG.md`: the milestone 1 notes had been copied into the old 2.0 and 1.0 sections by mistake.

**Things to remember**
- The camera can only be found by name or scan after milestone 4 gives its firmware `cam.local` and `/id`. Until then, put its IP address in `CAMERA_URL`.
- If a phone hotspot keeps devices apart, neither the name nor the scan can work. Then put the address from the Serial monitor in `.env`.

### 2026-10-05 — Session 3: easy setup (milestone 1)

**What we did**
1. **One place for the hotspot.** `.env` now has `WIFI_SSID` and `WIFI_PASS`, shared by both boards. The old `ROVER_WIFI_...` and `CAM_WIFI_...` settings are gone.
2. **`python -m earth_station.secrets`**: a helper that writes `rover1/secrets.h` and `cam1/secrets.h` from `.env`, and makes a long random rover token. Running it again is safe. It keeps an old copy as `secrets.h.bak`, which git also ignores.
3. **`python -m earth_station --check`**: tests the settings files, the rover, the camera and Jev. Each problem comes with a "fix:" line. It only ever sends the rover a `stop`, so nothing moves. `--check --sim` tries it on the fake rover.
4. **Rewrote the README Quick Start** in four parts: A just the laptop, B the real boards, C the real Jev, D Supabase (optional).
5. **13 new tests** (46 in total). We also tested a fresh copy of the project from zero to `--sim` by following the README.

**Things to remember**
- Until milestone 2, `--check` and the station use `ROVER_URL` (`http://rover.local`) and `CAMERA_URL` (the camera's IP, from its Serial monitor).
- Our own `.env` still has the old names: see "Next steps" step 2.

### 2026-10-05 — Session 2: the project plan (SPEC.md)

**What we did**
1. **Explained how the Earth Station works**: look → describe the photo → ask Jev → safety check → send the move → log it, about twice a second.
2. **Made four decisions** (see "Decisions so far"): phone hotspot, boards found by name, a mission control page, and the leader builds photo descriptions.
3. **Wrote `SPEC.md`**: the goal, a glossary, who does what, requirements, the target setup procedure and 9 milestones in build order.
4. **Added to `CLAUDE.md`**: follow the spec, work without the rover (simulator first, a hardware checklist for the teammate in firmware PRs), and teach as we build.
5. **Rewrote the README's laptop setup** as numbered beginner steps, and linked the spec.
6. **Connected the code to the real Jev** using TypeSafe's official docs. The old code listed the moves in the wrong field. Fixed, and 6 tests added. A key needs at least $5 of credits, about 40 hours of driving at 2 questions a second. The leader will buy credits later, so we use the pretend Jev for now.
7. **Added a `CLAUDE.md` rule:** Claude suggests `/clear` (a fresh chat) at good stopping points, after updating this diary.
8. **Wrote the rover's Jev Auto code** (milestone 3, firmware 2.1):
   - a Jev Auto button;
   - `/jev/cmd`, which takes moves from the laptop and checks the token;
   - a 1.5 s safety timer (watchdog), plus tilt and "too close" vetoes;
   - moves timed without `delay()`;
   - the extra sensor fields, and the `rover.local` name.

   It compiles in CI but hasn't run on the real rover yet. Also created a random rover token in `.env` and `rover1/secrets.h`.

**Things to remember**
- Real Jev: put the key in `.env` (`JEV_API_KEY`) and set `JEV_MODE=live`. Never paste it in chat or code. `DECIDE_EVERY_MS=1000` halves the cost.
- The leader has no rover right now, so laptop-side milestones (1, 2, 5, 6) can all be done before the hardware comes back.
- The rover's `secrets.h` now **must** have a `ROVER_CMD_TOKEN` line, or the rover code won't compile. It must equal `ROVER_CMD_TOKEN` in the laptop's `.env`. Share it privately, never on GitHub.
- ESP32 boards only see **2.4 GHz** WiFi. Set the phone hotspot to 2.4 GHz if it asks.

### 2026-10-04 — Session 1: clean-up, going public, Earth Station

**What we did**
1. **Read the project and reported its status.** It had rover code, camera code, an n8n AI workflow and a web dashboard.
2. **Removed n8n and the dashboard** from the laptop and from GitHub, and rewrote the README for what actually works.
3. **Collected the passwords and keys** into `.env`, a private file that never goes to GitHub.
4. **Made the repo ready for a team and for going public:**
   - Moved passwords and keys out of the rover and camera code into private `secrets.h` files.
   - Removed every old password and key from the project's whole history, then force-pushed (re-uploaded that history to GitHub).
   - Added team documents: `CLAUDE.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, `docs/ARCHITECTURE.md`, and a database safety file `docs/supabase/schema.sql`.
   - Added automatic checks on GitHub (CI). On every change they compile the rover and camera code and scan for leaked secrets.
5. **Learned what Jev is:** a fast AI from Typesafe that picks one answer from a short list, such as forward, left, right, back or stop. It reads only text, not pictures.
6. **Designed how Jev will drive the rover.** First 5 options, then the chosen plan: a laptop "Earth Station". Made two explainer pages, now in `docs/design/`.
7. **Built the Earth Station** (pull request #3, merged):
   - The `earth_station/` Python program.
   - A fake rover and camera for testing without hardware.
   - A pretend Jev for testing without an account.
   - A safety gate: if in doubt, stop.
   - A run log for each run, saved in `runs/`.
   - One-command setup scripts in `scripts/`.
   - 26 automatic tests, run on Windows, Mac and Linux.
8. **Made the repo public** after checking that no secret was left anywhere.
9. **Added instructions to `CLAUDE.md`:** explain everything for a beginner, explain each GitHub action, and update the README with every change.
10. **Started this `PROGRESS.md` diary.**

**Things to remember**
- Try the Earth Station: `.\.venv\Scripts\Activate.ps1`, then `python -m earth_station --sim`. Press `Ctrl+C` to stop.
- The rover and camera currently join **different** WiFi networks. For the Earth Station, all three devices (rover, camera, laptop) must be on the **same** one.
- The details about Jev's request format come from articles, not Typesafe's own docs, so check them when we get access.
