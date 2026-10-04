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
| Easy setup: hotspot typed once in `.env`, `--check` | ✅ Milestone 1 built (PR on `feat/easy-setup`) |
| Finding the boards automatically | ⏳ Milestone 2 (laptop only) |
| Rover code for "Jev Auto" mode | 🧪 Milestone 3: written (firmware 2.1, PR #7). Waiting for the teammate's hardware test |
| Photo descriptions (`earth_station/describe.py`) | ⏳ Milestone 5, now the leader's job (Claude vision) |
| Mission control page in the browser | ⏳ Milestone 6 |
| Real Jev connection | ✅ Code ready and tested against TypeSafe's docs. Waiting for a key ($5 of credits) |

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
- **`SPEC.md` is the plan.** Each pull request is one milestone from it.
- **Claude explains every step and every GitHub action in beginner-friendly words** (see `CLAUDE.md`).

## Next steps

The full build order is in `SPEC.md` section 6.

1. Merge the milestone 1 pull request (easy setup).
2. **Update your own `.env`:** it still uses the old names. Rename `ROVER_WIFI_SSID` to `WIFI_SSID` and `ROVER_WIFI_PASS` to `WIFI_PASS` (set them to the phone hotspot), and delete the `CAM_WIFI_...` lines. Then `python -m earth_station.secrets` and `python -m earth_station --check`.
3. Add the teammate as a collaborator on GitHub (repo → Settings → Collaborators), and send them `rover1/secrets.h` (or just the rover token) **privately**.
4. Teammate: flash firmware 2.1 and run the hardware checklist in PR #7.
5. **Real Jev:** buy $5 of credits at console.typesafe.ai, create a key, and put it in `.env` with `JEV_MODE=live`.
6. Milestones 2, 4, 5, 6: board finder, camera name, photo descriptions, mission control page.

---

## Session log

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
