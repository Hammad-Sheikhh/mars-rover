# 🚀 Mars Rover

![Supabase](https://img.shields.io/badge/Supabase-Integrated-green?style=flat-square&logo=supabase)
![ESP32](https://img.shields.io/badge/ESP32-Powered-blue?style=flat-square&logo=espressif)

**Chief Scientist: Hammad**

A two-board Mars rover. The main ESP32 drives the rover, avoids obstacles and logs sensor telemetry to Supabase. A separate ESP32-CAM captures images and uploads them to Supabase Storage. Each board also hosts its own WiFi access point with a local control/viewing page.

The **Earth Station** is a Python program on a laptop that lets the **Jev** AI drive the rover (*Jev Auto* mode), using the rover's telemetry and a description of what the camera sees.

📋 **The plan:** [SPEC.md](SPEC.md) has the requirements, the target setup (one phone hotspot, boards found automatically, a mission control page) and the milestones in build order.

---

## 🏗 System Architecture

```mermaid
graph TD
    subgraph Mars Rover
        ESP[ESP32 Main - rover1] -->|Telemetry every 5s| DB[(Supabase: sensor_readings)]
        CAM[ESP32-CAM - cam1] -->|JPEG every 10s| Stor[(Supabase Storage: rover_images)]
        CAM -->|Image URL| DB2[(Supabase: camera_captures)]
    end

    Phone1((Operator)) -->|AP: ESP32-Car-AP| ESP
    Phone2((Operator)) -->|AP: ESP32_CAM_MARS| CAM

    subgraph Laptop
        ES[Earth Station] <-->|next move| JEV[Jev AI]
    end
    ESP -->|/sensors/data| ES
    CAM -->|/capture| ES
    ES -->|/jev/cmd| ESP
```

## ✅ Current Status

| Component | Status |
|---|---|
| Rover firmware (`rover1/`) | ✅ Working |
| Camera firmware (`cam1/`) | ✅ Working |
| Supabase database + storage | ✅ Working |
| AP mode — rover control page | ✅ Working |
| AP mode — camera live view | ✅ Working |
| Earth Station (`earth_station/`) | 🧪 Runs on the simulator; rover firmware for Jev Auto is next |
| Real Jev connection | ✅ Ready: add your key to `.env` (see Quick Start step 5) |
| Photo descriptions (`describe.py`) | ⏳ Planned ([SPEC.md](SPEC.md) milestone 5) |
| Easy setup, board finder, mission control page | ⏳ Planned ([SPEC.md](SPEC.md) milestones 1, 2, 6) |

---

## 🛠 Features

### 🤖 Rover (`rover1/rover1.ino`)
*   **Autonomous Navigation**: Obstacle avoidance with an HC-SR04 ultrasonic sensor (median-of-3 filtering, back up and turn when closer than 40 cm).
*   **Manual Mode**: Forward/stop toggle from the control page.
*   **IMU Telemetry (MPU6050)**: Pitch, roll and terrain vibration via the `MPU6050_tockn` library, with gyro calibration on boot.
*   **Environmental Sensing**: Temperature and humidity (DHT11), pressure and relative altitude (BMP280), day/night (LDR).
*   **Event Log**: `last_event` field records `Obstacle Avoided`, `Tilt Warning`, `Impact Detected` or `Nominal`.
*   **Dual-Mode WiFi**:
    *   **AP Mode** (`ESP32-Car-AP`): Local control page at `http://192.168.4.1` with live telemetry.
    *   **Station Mode**: Posts readings to Supabase `sensor_readings` every 5 seconds.

### 👁 Camera (`cam1/cam1.ino`)
*   **ESP32-CAM (AI Thinker)**: VGA JPEG capture (falls back to CIF if PSRAM is not available).
*   **AP Mode** (`ESP32_CAM_MARS`): Live view page at `http://192.168.4.1`, refreshing every 3 seconds.
*   **Cloud Uplink**: Uploads a JPEG to the `rover_images` bucket every 10 seconds and saves its public URL in `camera_captures`.

### 🛰 Earth Station (`earth_station/`)
*   **Jev Auto**: twice a second, reads telemetry, reads the latest camera description, asks Jev for the next move and sends it to the rover.
*   **Two safety layers**: laptop-side gate (confidence, stale data, blocked path) plus the rover's own reflexes and watchdog.
*   **Runs anywhere**: built-in simulator and mock Jev, so it works on any laptop with no hardware or keys.
*   **Real Jev**: set `JEV_MODE=live` and your key in `.env` to let TypeSafe's Jev make the decisions, even against the simulator.
*   **Run logs**: every decision saved to `runs/*.jsonl` for replay.

Full guide: [docs/EARTH_STATION.md](docs/EARTH_STATION.md). Design walkthrough: open [docs/design/earth-station-plan.html](docs/design/earth-station-plan.html) in a browser.

---

## 📂 Project Structure

```text
mars-rover/
├── rover1/
│   ├── rover1.ino            # 🤖 Main rover firmware (ESP32)
│   └── secrets.example.h     # Credential template -> copy to secrets.h
├── cam1/
│   ├── cam1.ino              # 👁 Camera firmware (ESP32-CAM)
│   └── secrets.example.h     # Credential template -> copy to secrets.h
├── earth_station/            # 🛰 Laptop ground station (Python) + rover simulator
├── tests/                    # Earth Station tests (pytest)
├── scripts/                  # One-command setup: setup.ps1 (Windows), setup.sh (Mac/Linux)
├── docs/
│   ├── ARCHITECTURE.md       # Design, data model, pin map, security model
│   ├── EARTH_STATION.md      # Earth Station guide + rover protocol
│   ├── design/               # Design pages (open in a browser)
│   └── supabase/schema.sql   # Tables + row-level security policies
├── .github/                  # CI (compile + secret scan), PR/issue templates
├── pyproject.toml            # Earth Station package + tools
├── .env.example              # Credentials / endpoints / Earth Station settings
├── SPEC.md                   # The plan: requirements, target setup, milestones
├── CLAUDE.md                 # Guide for Claude Code / contributors
├── PROGRESS.md               # Project diary: what we did, decided, and what's next
├── CONTRIBUTING.md
├── SECURITY.md
└── CHANGELOG.md
```

---

## 🚀 Quick Start

### 1. Supabase Setup
Run [`docs/supabase/schema.sql`](docs/supabase/schema.sql) in the Supabase SQL editor. It creates:
*   **`sensor_readings`**: `temperature`, `humidity`, `ldr_state`, `pressure`, `altitude`, `pitch`, `roll`, `vibration`, `last_event`
*   **`camera_captures`**: `image_url`
*   **Storage bucket `rover_images`** (public)
*   **Row-level security**: the device (anon) key can only insert, never update or delete.

### 2. Credentials
Credentials never go in git. Each sketch reads them from a local, git-ignored `secrets.h`:

```sh
cp rover1/secrets.example.h rover1/secrets.h
cp cam1/secrets.example.h  cam1/secrets.h
```

Fill in the WiFi network, AP password and Supabase URL + **anon** key. Never use the `service_role` key on a device.

### 3. Firmware Deployment
Requires **ESP32 Arduino core 3.x** (uses the pin-based `ledcAttach` API).

*   **Rover**: Open `rover1/rover1.ino` and upload with board **ESP32 Dev Module**.
    *   Libraries: `Adafruit BMP280`, `Adafruit Unified Sensor`, `DHT sensor library`, `MPU6050_tockn`.
    *   I2C: SDA 25, SCL 26.
*   **Camera**: Open `cam1/cam1.ino` and upload with board **AI Thinker ESP32-CAM** (PSRAM enabled).

Keep the rover still while it powers on, because the gyro calibrates at boot.

### 4. Earth Station (any laptop, no rover needed)

1. Install **Python 3.11 or newer** from [python.org](https://www.python.org/downloads/). On Windows, tick **"Add Python to PATH"** in the installer.
2. Install **git** from [git-scm.com](https://git-scm.com/downloads).
3. Open a terminal (Windows: PowerShell) and get the project:
   ```sh
   git clone https://github.com/Hammad-Sheikhh/mars-rover.git
   cd mars-rover
   ```
4. Run the one-time setup. It creates a private Python install in `.venv/`, installs everything, and creates your `.env` settings file:
   ```sh
   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1   # Windows
   sh scripts/setup.sh                                          # macOS / Linux
   ```
   It should end with **"Setup done"**.
5. Turn on the private Python install (do this each time you open a new terminal):
   ```sh
   .\.venv\Scripts\Activate.ps1    # Windows
   . .venv/bin/activate            # macOS / Linux
   ```
   Your prompt now starts with `(.venv)`.
6. Try it with the built-in fake rover:
   ```sh
   python -m earth_station --sim
   ```
   You should see a pre-flight list of `OK` lines, then one line per decision, like `#7 turn_right 0.91 -> sent, rover ok`. Press `Ctrl+C` to stop.

To connect the real rover today, see [docs/EARTH_STATION.md](docs/EARTH_STATION.md). The simpler hotspot-based setup is planned in [SPEC.md](SPEC.md#5-setup-procedure-the-target).

### 5. Connect the real Jev (no rover needed)

1. Get a key: sign in at [console.typesafe.ai/keys](https://console.typesafe.ai/keys) and create an API key. Copy it.
2. Open `.env` in the repo folder and set:
   ```sh
   JEV_MODE=live
   JEV_API_KEY=<paste your key here>
   ```
   Save the file. `.env` never goes to GitHub, so the key stays private. Never paste it into code, issues or chat.
3. Test it with the fake rover (internet needed, no rover):
   ```sh
   python -m earth_station --sim
   ```
   The pre-flight should show `OK  Jev live` and `OK  Jev answering | <time> ms`. Each decision line is now the real Jev's choice.
4. If it fails, the pre-flight line says why: `rejected the API key` means the key is wrong, and `rate-limited` means wait a moment and try again. To go back to the offline stand-in, set `JEV_MODE=mock`.

---

## 🤝 Contributing & Security

*   Workflow, branch naming and commit style: [CONTRIBUTING.md](CONTRIBUTING.md)
*   The plan and build order: [SPEC.md](SPEC.md)
*   What we've done so far and what's next: [PROGRESS.md](PROGRESS.md)
*   System design and known gaps: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
*   Reporting vulnerabilities: [SECURITY.md](SECURITY.md). Please don't open public issues for these.

---

## 📌 Pin Map (Rover)

| Function | Pins |
|---|---|
| Motor driver | ENA 23, IN1 22, IN2 21, ENB 19, IN3 18, IN4 5 |
| Ultrasonic | TRIG 32, ECHO 35 |
| DHT11 | 27 |
| LDR | 33 (LED indicator 4) |
| I2C (MPU6050, BMP280) | SDA 25, SCL 26 |

---

## 🔧 Technology Stack

*   **Hardware**: ESP32, ESP32-CAM, MPU6050, BMP280, DHT11, HC-SR04, LDR module, L298N-style motor driver.
*   **Firmware**: C++ (Arduino framework).
*   **Backend**: Supabase (PostgreSQL + Storage).
*   **Earth Station**: Python 3.11+, `httpx`, Jev (Typesafe AI); `pytest` + `ruff`.

---

## 📜 License
MIT License.
