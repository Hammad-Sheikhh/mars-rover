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
| Rover code for "Jev Auto" mode | ⏳ Next job |
| Photo descriptions (`earth_station/describe.py`) | ⏳ Teammate's job |
| Real Jev connection | ⏳ Needs a Jev account and key |

**Who has what:** the teammate has the physical rover and camera. The project leader (repo owner) works on the laptop side.

## Decisions so far

- **Jev drives through a laptop (the "Earth Station")** on the same WiFi as the rover and camera. We chose this over cloud setups. *Why:* it's simplest, the fastest to react, and keeps keys off the rover.
- **No Vercel website.** Dropped on 2026-10-04.
- **Supabase will be removed** when the architecture changes later. So we don't rotate its key or invest more in it.
- **n8n and the old web dashboard were removed.** They weren't working.
- **The repo is public.** Passwords and keys live only in files that never go to GitHub: `.env`, `rover1/secrets.h` and `cam1/secrets.h`.
- **The leader merges their own pull requests.** A teammate review is welcome but not required.
- **Claude explains every step and every GitHub action in beginner-friendly words** (see `CLAUDE.md`).

## Next steps

1. Add the teammate as a collaborator on GitHub (repo → Settings → Collaborators).
2. Write the rover code for Jev Auto: a third button on its control page, a way to receive moves from the laptop (`/jev/cmd`), a safety timer, and sending `mode` and `distance_cm`. The rules are in `docs/EARTH_STATION.md`.
3. The teammate builds `describe.py` (photo → short description).
4. Get a Jev account and key, then switch `JEV_MODE` to `live` in `.env`.
5. Optional: a mission control page shown by the Earth Station in the laptop's browser.

---

## Session log

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
