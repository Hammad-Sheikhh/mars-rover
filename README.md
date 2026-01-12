# ESP32 Mars Rover

An advanced ESP32-based rover featuring dual-mode WiFi connectivity (AP for control, Station for telemetry), autonomous obstacle avoidance, and real-time environmental monitoring.

## Key Features

*   **Dual WiFi Modes:**
    *   **Access Point (AP):** Creates a local WiFi network ("ESP32-Car-AP") hosting a web server for low-latency manual control via a mobile-friendly web interface.
    *   **Station (STA):** Connects to an existing WiFi network to log sensor data to the cloud.
*   **Control Modes:**
    *   **Manual:** Web-based joystick/button control for movement (Forward, Backward, Left, Right, Stop) and speed adjustment.
    *   **Autonomous:** Intelligent obstacle avoidance using Ultrasonic and IR sensors to navigate without human intervention.
*   **Telemetry:** Real-time streaming of data:
    *   Temperature & Humidity (DHT11)
    *   Pressure & Relative Altitude (BMP280)
    *   Light Levels (LDR)
*   **Cloud Integration:** Periodically sends sensor data to an n8n webhook (or any compatible API) for logging and analysis.

## Hardware Requirements

*   **Microcontroller:** ESP32 Development Board
*   **Motor Driver:** L298N or similar
*   **Motors:** 2x or 4x DC Motors + Robot Chassis
*   **Distance Sensor:** HC-SR04 Ultrasonic Sensor
*   **Obstacle Sensors:** 2x IR Sensors (Left/Right)
*   **Environmental Sensors:**
    *   BMP280 (Pressure/Altitude)
    *   DHT11 (Temperature/Humidity)
    *   LDR Sensor Module (Light)
*   **Power Supply:** Suitable battery pack (e.g., 2x 18650 Li-ion batteries)

## Pin Configuration

Based on the default configuration in `rover1.ino`:

### Motor Driver (L298N)
| ESP32 Pin | Function |
| :--- | :--- |
| GPIO 23 | Motor A Enable (ENA) - PWM |
| GPIO 22 | Motor A Input 1 |
| GPIO 21 | Motor A Input 2 |
| GPIO 19 | Motor B Enable (ENB) - PWM |
| GPIO 18 | Motor B Input 3 |
| GPIO 5 | Motor B Input 4 |

### Sensors
| Component | ESP32 Pin | Notes |
| :--- | :--- | :--- |
| **Ultrasonic** | | |
| Trig | GPIO 32 | |
| Echo | GPIO 35 | |
| **IR / Edge** | | |
| Left Sensor | GPIO 17 | |
| Right Sensor | GPIO 16 | |
| **Environment** | | |
| LDR | GPIO 33 | Digital Output from module |
| LDR LED | GPIO 4 | Status Indicator |
| DHT11 | GPIO 27 | Data Pin |
| BMP280 SDA | GPIO 25 | I2C Data |
| BMP280 SCL | GPIO 26 | I2C Clock |

## Setup & Configuration

1.  **Install Libraries:**
    Ensure you have the following libraries installed in your Arduino IDE:
    *   `Adafruit BMP280 Library`
    *   `DHT sensor library`
    *   `Adafruit Unified Sensor`

2.  **WiFi Configuration:**
    Open `rover1.ino` and update the following lines with your WiFi credentials (for data logging):
    ```cpp
    const char* wifiSSID = "YOUR_WIFI_SSID";
    const char* wifiPass = "YOUR_WIFI_PASSWORD";
    ```

3.  **Webhook Configuration:**
    Update the `n8nWebhookUrl` variable if you wish to change the data destination:
    ```cpp
    const String n8nWebhookUrl = "https://your-n8n-instance.com/webhook/...";
    ```

4.  **Upload:**
    Connect your ESP32 and upload the sketch.

## Usage

1.  **Power On:** Turn on the rover.
2.  **Connect:** Connect your phone/laptop to the WiFi network `ESP32-Car-AP` (Password: `REDACTED_AP_PASS`).
3.  **Control:** Open a web browser and navigate to `192.168.4.1`.
4.  **Drive:** Use the on-screen controls to drive or switch to "Autonomous" mode.