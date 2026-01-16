# ESP32 Mars Rover

An advanced ESP32-based rover featuring dual-mode WiFi connectivity, autonomous obstacle avoidance, and real-time cloud telemetry via **Supabase**.

![Supabase](https://img.shields.io/badge/Supabase-Integrated-green?style=flat-square&logo=supabase)
![ESP32](https://img.shields.io/badge/ESP32-Powered-blue?style=flat-square&logo=espressif)

## Key Features

*   **Dual WiFi Modes:**
    *   **Access Point (AP):** Creates a local network (`ESP32_CAM_MARS`) for low-latency manual control via phone.
    *   **Station (STA):** Connects to home WiFi to upload data and images to the cloud.
*   **Cloud Integration (Supabase):**
    *   **Telemetry:** Sensors (Temp, Humidity, Pressure, Altitude, Light) logged to `sensor_readings` database table.
    *   **Vision:** Periodic images captured and uploaded to `rover-images` Storage bucket.
*   **AI Analysis Workflow:**
    *   Includes an n8n workflow (`workflows/mars_rover_report.json`) that combines the latest sensor readings and images to generate a scientific status report using Generative AI.
*   **Control Modes:**
    *   **Manual:** Web-based joystick control.
    *   **Autonomous:** Obstacle avoidance using Ultrasonic and IR sensors.

## Hardware Requirements

*   **Microcontroller:** ESP32 Development Board (Main Rover)
*   **Camera Module:** ESP32-CAM (AI-Thinker Model)
*   **Motor Driver:** L298N
*   **Sensors:** HC-SR04 (Ultrasonic), 2x IR Sensors, BMP280, DHT11, LDR Module
*   **Power:** 2x 18650 Li-ion batteries

## Project Structure

```text
mars-rover/
├── README.md               # Project documentation
├── workflows/              # Automation workflows
│   └── mars_rover_report.json  # n8n workflow for AI analysis
├── rover1/                 # Main Rover Code (Motors + Sensors)
│   └── rover1.ino
└── cam1/                   # Camera Code (Image Capture + Upload)
    └── cam1.ino
```

## Setup & Configuration

### 1. Supabase Setup
1.  Create a Supabase project.
2.  **Database:** Create a `sensor_readings` table and a `camera_captures` table.
3.  **Storage:** Create a public bucket named `rover-images`.
4.  **Policies:** Enable RLS policies to allow `anon` key to INSERT rows and files.

### 2. ESP32 Configuration
Update the `ssid`, `password`, `supabaseUrl`, and `supabaseKey` in both `rover1.ino` and `cam1.ino`.

### 3. AI Workflow (n8n)
Import `workflows/mars_rover_report.json` into n8n.
*   No external webhook setup needed on the rover (it uploads directly to Supabase).
*   The workflow triggers via webhook (or manually) to fetch the **latest 5 readings** and analyzing the **latest image**.