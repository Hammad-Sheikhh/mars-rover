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
| Earth Station (laptop program that lets Jev drive) | ✅ Drive commands, safety vetoes and board finding verified on the real rover. Full AI drive = Milestone 8 |
| Project plan (`SPEC.md`) | ✅ Written. Milestones 0–8 |
| Easy setup: hotspot typed once in `.env`, `--check` | ✅ Milestone 1 merged (PR #8) |
| Finding the boards automatically | ✅ Milestone 2 merged (PR #9). Tested on the simulator |
| Camera name `cam.local` and `/id` | ✅ Hardware-tested 19–20 Oct: found by name, `/id` answered, photos upload, live view works even with no hotspot (PR #10 checklist complete) |
| Rover code for "Jev Auto" mode | ✅ Hardware-tested 19–20 Oct: whole PR #7 checklist passed (driving, obstacle veto, watchdog, token) |
| Photo descriptions with Gemini vision (`earth_station/describe.py`) | ✅ Merged (PR #20) and **live-tested with the real Gemini key**: 2.4 s per description, same four-field shape for Jev. Camera-timing coherence fixed (PR #21). Bench built; run it on the flipped camera before milestone 8 |
| Camera + vision bench (`earth_station/bench.py`) | ✅ Built 20 Oct: smoke / stamina / ground-truth probes / rate-limit burst, PASS/FAIL verdict, 120 tests. Awaits the standalone camera to run for real |
| Mission control page in the browser, with STOP | ✅ Milestone 6 (PR #17), now upgraded (PR #19): the page explains every decision in plain words, four steps, plus a recent-decisions table |
| Real Jev connection | ✅ Key works (first real call: 571 ms). Spending guard merged (PR #15) |

**Who has what (updated 2026-10-20):** the project leader now has **all the hardware**: rover, camera and laptop. The teammate was no longer sent the rover token since they don't flash anything for now. Hardware tests are done in person by the leader.

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
- **Photo descriptions run on Gemini's free tier** (2026-10-20). New `VISION_PROVIDER` setting: `gemini` (free key from Google AI Studio, one photo every ~5 s) or `anthropic` (the old paid Claude path, kept working). `VISION_FOCUS` names the objects that matter. *Why:* Jev only needs a short, honest description; the free tier makes it $0, and enabling billing later changes nothing in the code.
- **Commit early and often, theme-wise** (2026-10-20), a standing rule now in `CLAUDE.md` and `CONTRIBUTING.md`. *Why:* many small, themed commits are easier to review, revert and understand than one big one.
- **Jev spending guard** (2026-10-06): each run makes at most `JEV_MAX_CALLS` real Jev calls (default 20), then stops the rover and ends. `--sim` uses the pretend Jev unless you add `--live-jev`. Tests never call the real Jev. *Why:* credits cost money, and the leader wants very careful use while we build.
- **`SPEC.md` is the plan.** Each pull request is one milestone from it.
- **The leader's manual tasks aren't written here until they're confirmed done** (2026-10-06). Claude keeps the open ones in its private memory and asks about them every session (see `CLAUDE.md`). *Why:* the diary should only say what really happened.
- **Claude explains every step and every GitHub action in beginner-friendly words** (see `CLAUDE.md`).

## Next steps

The full build order is in `SPEC.md` section 6.

1. **Milestone 8 — the first real drive.** First a short live-Jev run on the simulator (`python -m earth_station --sim --live-jev`, `JEV_MAX_CALLS=10`) so we can watch the AI's choices safely, then the real rover on the floor in an open area with a person next to it.
2. ~~Resume the parked, half-finished mission-control work~~ **Done today, PR #19 merged.**
3. ~~Later: a free way for the camera to help Jev~~ **Built and live-tested with the real Gemini key.** Now: flash the camera with the Arduino IDE steps (they're in the leader's task notes), then run `python -m earth_station.bench all` on it, and on a pass go to milestone 8 (first real drive with vision).

---

## Session log

### 2026-10-20 — Session 12: the camera's eyes go free (Gemini vision)

**What we did**

1. **Chose the vision provider.** Compared Claude, Gemini, Groq and OpenRouter free tiers for the camera-photo job. Picked **Gemini Flash-Lite on the free tier**: a direct describer (no thinking — Jev does the reasoning), the best small-image quality of the free options, a no-credit-card key, and a cheap paid fallback (~$0.05–0.12 per driving hour) that needs no code change.
2. **`describe.py` now speaks two providers.** New setting `VISION_PROVIDER` (`gemini` or `anthropic`); Claude's path is untouched. The Gemini path sends the photo straight to `generativelanguage.googleapis.com` with the existing `httpx2` library (no new packages), the same four-field answer schema in Gemini's own `responseSchema` dialect, and `thinkingBudget: 0` (no thinking, just describe). Errors translate into the same plain messages: wrong key, rate limit (try a bigger `CAMERA_EVERY_MS`), offline, cut-off answer, refusal, or a non-JSON answer.
3. **New `VISION_FOCUS` setting.** A comma-separated list (e.g. `cables on the floor, stairs or drops, pet or person's feet`) is added to the photo prompt for **both** providers, so Jev reads descriptions biased towards the objects our rooms actually hold. The four-field answer shape and the safety gate are unchanged.
4. **Tests grew with it.** A `FakeGemini` answers like the real API: good scene, request shape (photo + schema + focus line + no thinking), not-a-JPEG refused before a call, SAFETY/MAX_TOKENS/not-JSON answers, and every HTTP problem (bad key, 429, 500, connection, timeout) mapping to its message. Tests are now sealed from the developer's own `.env` (`VISION_PROVIDER`, `VISION_FOCUS` deleted per test). **108 tests all pass**, ruff clean.
5. **Docs updated everywhere:** `.env.example` (Gemini defaults + a free-tier photo-rate note), README status table and Quick Start part D (Gemini free first, Claude as the paid alternative), `docs/EARTH_STATION.md` settings table, `CHANGELOG.md` (Unreleased).
6. **New standing rule, written into `CLAUDE.md` and `CONTRIBUTING.md`: commit early and often, theme-wise.** Every finished theme becomes its own commit once checks pass; unrelated changes are never mixed.

**Added later the same day (the leader handed over a real Gemini key, named `roverv3`):**

7. **Live with a real key.** Wrote the key into `.env` without printing it, switched on `DESCRIBE_MODE=live`/`VISION_PROVIDER=gemini`, and described a synthetic 640×480 "room" photo: **2.4 s**, correct JSON (`pillar directly ahead, side open`).
8. **The first real-model bug in the wild:** Gemini Flash-Lite rejects `thinkingBudget: 0` with a 400 ("invalid argument") - it can't switch thinking off. Found with a direct REST diagnostic; fixed by sending `thinkingBudget` only to models that accept it (`_gemini_disables_thinking`). 110 tests. Merged as part of PR #20 (all 6 CI checks green).
9. **Timing research found a real config bug:** the photo loop is `capture -> describe (~2.5 s) -> sleep`, so the true photo period is `CAMERA_EVERY_MS + 2.5 s`; with the old `SCENE_MAX_AGE_MS=3000` the gate would stop Jev for "camera description too old" most of the time. Fixed both to coherent values: `CAMERA_EVERY_MS=3000` (period ~5.5 s ~= 11 req/min, inside the free Flash-Lite tier) and `SCENE_MAX_AGE_MS=6500`. Merged as **PR #21** (all 6 checks green).
10. **Grounded the timing with research:** Google no longer publishes per-model free-tier numbers (per project, see your AI Studio page); Flash-Lite snapshots say ~15 RPM / 1,000-1,500 RPD; the arXiv ESP32-CAM benchmark says VGA streams at 14 fps / ~15 KB and stays the sweet spot (SVGA is 8 fps, UXGA 1.3 fps - no benefit for stills); streaming to the vision API is out (the bottleneck is the 2.4 s API trip and the rate limit, not fps), a local MJPEG stream stays a later live-view nicety.
11. **Built the reliability bench** (`python -m earth_station.bench`): `smoke`, `stamina` (fresh-scene coverage + 429 handling), `scene` ground-truth probes (box ahead/left/right, covered lens, cable) scored against reality, and `burst` to find the exact 429 point and prove the calm cadence recovers. JSON events in `runs/vision-bench-*.jsonl`, final PASS/FAIL verdict. 15 new tests (120 total), and the sleeps that would block tests are named constants the tests shorten. Merged as **PR #22**.
12. **First live bench run on the real camera — and it caught a real hardware bug on day one.** After the leader's Serial-monitor garbling turned out to be just a baud mismatch (115200 fixes it; camera had flashed fine) and both laptop and camera moved onto the phone hotspot: 5/5 smoke photos captured and described with sensible answers ("ceiling fan and wall directly ahead"), describe success 100%, steady-state describe 1.4–2.5 s, scene freshness **100%** inside the 6.5 s window. But capture latency was bimodal: 192–478 ms normally, 1–2 s whenever a capture collided with the firmware's 10-second Supabase-upload cycle (TLS handshake starves the web server) — capture p95 FAIL at 2 s. The 4.3 s describe outlier was only the first call's cold HTTPS connection.
13. **Fixed it in firmware 2.2.0:** the periodic Supabase upload is off by default (`SUPABASE_UPLOAD 0`); its job is done better by live vision descriptions + JSONL logs, and it burned ~8,600 uploads/day for nothing. The camera now serves `/capture` with nothing else on the radio. Needs one re-flash (the leader has the IDE open anyway), then the bench re-runs to verify capture p95 under 1 s.

**Things to remember**
- Gemini's free tier is happiest at a photo period of ~5.5 s on this rover: `CAMERA_EVERY_MS=3000` **must** stay smaller than `SCENE_MAX_AGE_MS=6500` (the true period is CAM + ~2.5 s of describe time). If one changes, change the other.
- Gemini's API returns an invalid key as **HTTP 400** with "API key not valid" in the body — the code reads that body before calling it a key problem.
- Gemini Flash-Lite **cannot switch thinking off** (`thinkingBudget: 0` = 400). Only non-"lite" Flash models take the budget.
- `gemini-flash-lite-latest` is a rolling alias, so it won't break when Google renames Flash models (the 2.5 series is being phased out right now).
- Free-tier numbers now live only inside your AI Studio project page; any table without a date is archaeology. Rate limit is per project, not per key.
- RPD is the real two-hour-a-day budget: ~660 descriptions per driving hour at ~11 req/min. Bench phases and sim runs on `DESCRIBE_MODE=mock` burn nothing.

---

### 2026-10-20 — Session 11: mission control explains itself (PR #19 merged)

1. **Resumed the parked work from session 9.** Switched to branch `feat/mission-control-readable` and restored the stashed changes with `git stash pop` (a stash is a safe drawer for uncommitted work). The code turned out to be finished: 91 tests passed and ruff (the style checker) was clean.
2. **The mission-control page now explains every decision in plain words:**
   - a one-sentence story line at the top ("The way ahead is clear (104 cm), so Jev chose forward and the rover is driving forward.");
   - four left-to-right panels: what the rover sees (distance + a red/amber/green gauge against the 30 cm safe distance) → what Jev chose (with its confidence) → what the safety gate did (every gate reason translated into plain words) → what the rover did;
   - a table of the last 20 decisions (newest first) with a colour-coded result chip;
   - the exact words the station sends to Jev (it's everything Jev knows);
   - confidence bars with a marker line showing `min_confidence`.
3. **Everything is verified against the real strings:** the page's plain-word reasons match `safety_gate.py`, and the "Distance ahead:" regex matches `state_text.py`, so no explanation can drift out of sync silently. 2 new tests (91 total).
4. **Docs updated in the same PR:** README features, `CHANGELOG.md` (Unreleased), `SPEC.md` milestone 6 row. A second `docs:` commit also fixed `SPEC.md` rows 3–4, which still said "waiting for the hardware test" although session 9 (19–20 Oct) passed both checklists.
5. **All 6 CI checks green; merged PR #19** with `gh pr merge`. Also fixed a form typo in the PR body (had wrongly ticked "rover1 firmware"; laptop-only change).
6. **Live smoke check:** ran `--sim --no-browser` for 25 seconds; `/state` answered 200 with 20 history entries, `told_jev` text and the limits — everything the new panels need.
7. **Branch cleanup after the merge:** deleted the merged local branches (`feat/mission-control-readable`, plus stale `feat/jev-live` and `feat/rover-jev-auto`) and 9 fully-merged branches on GitHub (`docs/*` and `feat/*` ones left over from earlier PRs). Only `main` remains on both sides.

6. **Added later the same day (leader):**
   - **Repo description cleaned up:** GitHub showed the project starting with "RED FLAG:"; replaced so it now starts with "a two-board ESP32 Mars rover...". No code changed.
   - **No more open manual tasks:** the leader confirmed the teammate doesn't need the rover token any more, because **the leader now has the rover and all the hardware**. The task (open since 2026-10-05) is closed without being done. The "Who has what" line above was updated: hardware tests are done in person by the leader from now on.

**Things to remember**
- Stashes live only in the machine and repo copy that made them — restoring quickly is kinder to future sessions than leaving them parked.
- PowerShell turns git's stderr progress lines (like `remote:`) into scary-looking red "NativeCommandError" text. Harmless; the command succeeded.
- Mission control's plain-word reasons depend on the exact gate reason strings; if `safety_gate.py` ever gets a new reason, add a translation in `mission_control.html` (`plainReason`) and a test.

---

### 2026-10-20 — Session 10: admin clean-up (PR #2 merged)

1. **Merged PR #2** (Dependabot: `actions/checkout` v5 → v7 in the CI workflow). Before merging we checked the one breaking change in v6/v7 — it only affects `pull_request_target` workflows, and ours uses plain `push`/`pull_request`, so it was safe. All 6 CI checks on the PR were green. The GitHub MCP token could not merge (read-only), so `gh pr merge` from the laptop did it.
2. **Housekeeping after the merge:** brought local `main` up to date, deleted the merged local branches (`docs/session-9-hardware-checks`, `docs/spec`) and the Dependabot branch on GitHub.
3. The repo description on GitHub still starts with "RED FLAG:". Left as is for now; ask whether it's deliberate.

---

### 2026-10-19/20 — Session 9: firmware 2.1 on real hardware (milestones 3 and 4 checked)

The boards were with the leader. Both were flashed from `main` (firmware 2.1).

**What we did**
1. **All 12 `--check` checks passed on real hardware:** rover and camera found **by name** on the phone hotspot (`rover.local`, `cam.local`), token accepted, camera photo served (9.4 KB). This answers the diary's open question "does `.local` work on the hotspot?" — **yes**.
2. **Whole rover checklist (PR #7) passed:** control page shows V2.1 and a live obstacle distance; Jev Auto toggles on (page badge, no wheel movement); all four drive commands from the laptop (forward, turn_left, turn_right, reverse) in one short self-stopping move each; holding a hand 10 cm in front of the sensor, `forward` was refused with `obstacle_too_close` (wheels still) and allowed again when the hand was removed; with Jev Auto off the move was refused `not_in_jev_mode`; with one character of the token twisted in `.env` the move was refused `bad_token` (HTTP 401), then `.env` was restored byte-identically (SHA-256 comparison, no secrets shown); one clean `forward` at the end.
3. **Whole camera checklist (PR #10) passed:** found at `cam.local`, `/id` correct, photos upload to Supabase continuously (arriving in the table live), live view works on the camera's own AP. The camera joined the new hotspot without issues.
4. **New hotspot:** `.env` and `rover1/secrets.h` were edited by hand and verified to match (hash comparison of values, nothing printed). Reminder learned: when the hotspot changes, both `secrets.h` files need it too — `python -m earth_station.secrets` keeps them in sync from `.env`.
5. **Investigated "the readings table isn't updating":** not a bug. The rover's Serial showed `Data sent to Supabase successfully!`, and that line only prints on HTTP 201 — Supabase's "row created". No 400 ever appeared, and the payload matches the table's columns. The SQL editor showed the truth: **591 rows, newest one from the minute the board was powered down**. The confusion was the Supabase Table Editor showing only 100 rows per page, **oldest first** — new rows were on later pages. About 100 old rows were deleted while finding this out (harmless: data from the old firmware days, never shown).
6. **Parked half-finished work:** branch `feat/mission-control-readable` carried uncommitted changes (the page would show the last 20 decisions and what Jev was told). Now stashed away safely on that branch to be resumed after Milestone 8.
7. **New open PR:** #2 bumps the CI `actions/checkout` tool version (security/dependency bot). Not related to our work; merge whenever.

**Things to remember**
- **Supabase Table Editor shows 100 rows per page, oldest first.** To see the latest rows: sort `created_at` descending, or run `select * from sensor_readings order by created_at desc limit 20;` in the SQL editor. **Never delete rows to find new ones.**
- **HTTP 201 from the rover's POST is proof of an inserted row**; the firmware prints "successfully!" only on 201.
- The rover dropped off the hotspot once mid-session (name lookup and scan both missed it for ~a minute, then it was back at the same IP). Boards self-recover; if it happens often, fix it by setting `ROVER_URL=http://<ip>` in `.env`.
- Serial monitor garbling (random lines of dots) at 115200 baud is cosmetic, not a fault.

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
