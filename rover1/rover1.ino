
#include <Wire.h>
#include <WiFi.h>
#include <WebServer.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BMP280.h>
#include <DHT.h>
#include <HTTPClient.h> 
#include <MPU6050_tockn.h> // NEW: IMU Library
#include <ESPmDNS.h>        // lets the laptop find us as rover.local
#include "secrets.h"        // credentials (git-ignored) - copy secrets.example.h to secrets.h
// ---------- WiFi Station (for internet) ---------- // NEW
const char* wifiSSID = WIFI_SSID;
const char* wifiPass = WIFI_PASS;
// ---------- Supabase Configuration ----------
// Periodic sensor uploads are OFF by default (firmware 2.2.0, same fix as the camera):
// the blocking TLS handshake every 5 s starved the web server, making /sensors/data
// and /jev/cmd time out mid-drive. Telemetry is recorded by the Earth Station's
// JSONL run logs instead. Turn back on (SUPABASE_UPLOAD 1) only while debugging.
#ifndef SUPABASE_UPLOAD
#define SUPABASE_UPLOAD 0
#endif
const String supabaseUrl = SUPABASE_URL;
const String supabaseKey = SUPABASE_ANON_KEY;
// ---------- Data Send Interval ----------
unsigned long lastSendTime = 0;
const unsigned long sendIntervalMs = 5000; // Send every 5 seconds
// ---------- WiFi AP ----------
const char* apSSID = AP_SSID;
const char* apPass = AP_PASS;
WebServer server(80);                   // class/object/port 80 is standard path for http traffic
// ---------- Jev Auto (the Earth Station laptop drives) ----------
#ifndef ROVER_CMD_TOKEN
#error "Add ROVER_CMD_TOKEN to rover1/secrets.h (see secrets.example.h)"
#endif
const char* roverCmdToken = ROVER_CMD_TOKEN;  // laptop must send this in the X-Token header
const char* FIRMWARE_VERSION = "2.5.3";
const char* MDNS_NAME = "rover";              // reachable as http://rover.local on the hotspot
const unsigned long JEV_WATCHDOG_MS = 1500;   // no command for this long -> stop
const unsigned long JEV_MAX_MOVE_MS = 500;    // longest single move
const long JEV_MIN_FORWARD_CM = 20;           // never drive forward closer than this
const unsigned long DISTANCE_EVERY_MS = 60;   // background ultrasonic sampling
// ---------- Motor Pins ----------
const int ENA = 23;
const int IN1 = 22;
const int IN2 = 21;
const int ENB = 19;
const int IN3 = 18;
const int IN4 = 5;
// PWM (ledc) settings
const int PWM_FREQ = 5000;      // pulse 5000 times per second
const int PWM_RES = 8; // 0-255  --> 256 levels of speed
// ---------- Ultrasonic Pins ----------
const int TRIG_PIN = 32;
const int ECHO_PIN = 35;
// ---------- MPU6050 ----------
MPU6050 mpu(Wire);
float vibrationScore = 0;
float lastAccX = 0, lastAccY = 0;
const float ROLLOVER_LIMIT = 35.0;
const float IMPACT_THRESHOLD = 0.5;
String lastEvent = "Nominal";
// An event is news for a short while, then history: without this an old
// "Tilt Warning" stayed in every telemetry payload (and in every Jev brief)
// indefinitely, and Jev kept reading a hazard that was long over.
const unsigned long EVENT_FRESH_MS = 8000;   // an event is reported this long
unsigned long lastEventMs = 0;
void markEvent(const char* name) {           // stamp when an event happens
  lastEvent = name;
  lastEventMs = millis();
}
void expireOldEvent() {                      // called every loop: expire stale events
  if (lastEvent != "Nominal" && millis() - lastEventMs > EVENT_FRESH_MS) {
    lastEvent = "Nominal";
    lastEventMs = 0;
  }
}
// Real orientation comes from the accelerometer (the gravity vector), NOT from
// the library's getAngleX()/getAngleY(). Those are 99.6% integrated gyro: the
// rotation sum sticks at fake values (e.g. -90) after wobble or handling and
// then poisons everything - tilt vetoes, Tilt Warning events, Jev's briefs.
// atan2 on the accelerometer is drift-free and instant; a light low-pass keeps
// motor vibration from spiking it.
float pitchDeg = 0.0, rollDeg = 0.0;
bool anglesPrimed = false;
void refreshAngles() {
  float ax = mpu.getAccX();
  float ay = mpu.getAccY();
  float az = mpu.getAccZ();
  float pitchNow = atan2(ay, az + abs(ax)) * 57.29578;    // same formula the library uses for its accelerometer angle
  float rollNow = atan2(ax, az + abs(ay)) * -57.29578;
  if (!anglesPrimed) {                    // first reading: start exactly on it
    pitchDeg = pitchNow;
    rollDeg = rollNow;
    anglesPrimed = true;
  } else {
    pitchDeg = 0.7f * pitchDeg + 0.3f * pitchNow;
    rollDeg = 0.7f * rollDeg + 0.3f * rollNow;
  }
}
// ---------- LDR Pins ----------
const int LDR_PIN = 33; // digital OUT from LDR module
const int LDR_LED = 4; // indicator GPIO (LED is disconnected for now)
// ---------- DHT11 ----------
const int DHT_PIN = 27;
DHT dht(DHT_PIN, DHT11);       // class--object-- constructor parameters 
// ---------- BMP280 ----------
Adafruit_BMP280 bmp;           // class-object
bool bmpFound = false;
float bmpBaselinePressure = 101900.0; // Pa, Pressure of islamabad
float baselineAltitudeM = 0.0; // 
// ---------- Behavior ----------
volatile bool autonomousEnabled = false;
volatile bool roverMoving = false;         // for the simple forward button
volatile bool jevEnabled = false;          // Jev Auto: moves come from the laptop
bool hasLastJevSeq = false;                // to ignore a retried command
long lastJevSeq = 0;
unsigned long lastJevCmdMs = 0;            // watchdog timer
bool jevMoving = false;                    // a Jev move is running
String jevAction = "stop";
unsigned long jevMoveStartMs = 0;
unsigned long jevMoveMs = 0;
long distSamples[3] = {-1, -1, -1};        // last 3 ultrasonic readings
int distIndex = 0;
long lastDistanceCm = -1;                  // median of distSamples, -1 = no echo
unsigned long lastDistanceMs = 0;
const int FORWARD_SPEED = 200;
const int SAFE_DISTANCE_CM = 40;
const int DEFAULT_SPEED = 180;
const int TURN_SPEED = 230;
const int BACKUP_TIME_MS = 430;
const int TURN_TIME_MS = 600;
// ---------- Forward declarations ----------
void handleRoot();
void handleStartNavigation();
void handleStartStopRover();
void handleSensorsData();
void notFound();
long getDistance();
long singleUltrasonicReading();
void forward(int speed);
void backward(int speed);
void leftTurn(int speed);
void rightTurn(int speed);
void stopMotors();
void sendDataToSupabase(); // Function to send sensor data to Supabase
void handleStartJev();
void handleJevCmd();
void handleId();
void setJevMode(bool on);
void jevLoop();
void runJevMove(const String& action, int speed, unsigned long ms);
void stopJevMove();
bool isTilted();
void sampleDistance();
long medianOf3(long a, long b, long c);
String roverMode();
void setup() {
  Serial.begin(115200);
  delay(100);
  Serial.printf("\n=== Rover firmware %s ===\n", FIRMWARE_VERSION);   // 2.5.3: first line tells you WHICH sketch is running
  // Motor pins
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  // PWM setup (core 3.x pin-based LEDC API)
  ledcAttach(ENA, PWM_FREQ, PWM_RES);   // attaches PWM directly to the pin, no channel needed
  ledcAttach(ENB, PWM_FREQ, PWM_RES);
  // Sensors pins
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(LDR_PIN, INPUT);
  pinMode(LDR_LED, OUTPUT);
  digitalWrite(LDR_LED, LOW);
  digitalWrite(TRIG_PIN, LOW);
  stopMotors();
  // DHT11
  dht.begin();  // handshake of sensor with libraries 
  // I2C on GPIO25 (SDA) and GPIO26 (SCL)
  Wire.begin(25, 26);
  // MPU6050 //bmp
  mpu.begin();
  Serial.println("Calibrating IMU... Keep rover still");
  mpu.calcGyroOffsets(true);  /* 
  Sampling: The ESP32 quickly reads the sensor 200 times in a row.
Averaging: It calculates the average of those 200 readings.
The "Correction": This average is saved as the Offset. From now on, every time the MPU reads a value, it automatically subtracts that Offset*/
  // Initialize BMP280 (try both addresses)
  if (bmp.begin(0x76)) {
    bmpFound = true;
    bmpBaselinePressure = bmp.readPressure();
    baselineAltitudeM = bmp.readAltitude(101325.0); // baseline vs sea level
    Serial.print("BMP280 @0x76, baseline alt (m): ");
    Serial.println(baselineAltitudeM, 4);
  } else if (bmp.begin(0x77)) {
    bmpFound = true;
    bmpBaselinePressure = bmp.readPressure();
    baselineAltitudeM = bmp.readAltitude(101325.0);
    Serial.print("BMP280 @0x77, baseline alt (m): ");
    Serial.println(baselineAltitudeM, 4);
  } else {
    bmpFound = false;
    Serial.println("BMP280 not found (0x76/0x77).");
  }
  // NEW: Set WiFi to dual mode (AP + Station)
  WiFi.setHostname(MDNS_NAME);    // must be set BEFORE mode()/begin() (ESP32 docs)
  // 2.5.3: this is the exact sequence a standalone radio test proved on this
  // board: mode -> disconnect() -> begin. Firmware 2.5.1/2.5.2 called
  // setSleep(false) and disconnect(true) BEFORE the radio was started, which
  // put the ESP-IDF driver into a "Set status to INIT" reset loop: the radio
  // never joined the hotspot and never even raised its own AP.
  WiFi.mode(WIFI_STA);            // join the hotspot alone; the AP comes up afterwards
  WiFi.disconnect();              // no wifioff - clear any half-state, keep the driver running
  // NEW: Connect to WiFi (station mode) for internet
  WiFi.begin(wifiSSID, wifiPass);
  Serial.print("Connecting to WiFi station...");
  int wifiAttempts = 0;
  while (WiFi.status() != WL_CONNECTED && wifiAttempts < 40) { // 40 x 0.5 s = 20 s (2.5.2: was 10 s - a slow phone needs longer)
    delay(500);
    Serial.print(".");
    wifiAttempts++;
    if (wifiAttempts % 10 == 0) Serial.printf(" (status %d)\n", WiFi.status()); // 0=idle 1=no-sid 4=ok 5=failed 6=wrong-pass 7=assoc-lost... tell-tale when it won't join
  }
  if (WiFi.status() == WL_CONNECTED) {    // checks if esp is connected to wifi
    Serial.println("\nWiFi station connected. IP: " + WiFi.localIP().toString());  // print ip
    WiFi.setSleep(false);                 // 2.5.0: modem sleep made ping jitter. Valid only AFTER start - see note above
    WiFi.mode(WIFI_AP_STA);               // station is stable - now bring our own AP up beside it
#if !SUPABASE_UPLOAD
    Serial.println("Supabase uploads are off (SUPABASE_UPLOAD 0): the rover only serves control + Jev.");
#endif
    if (MDNS.begin(MDNS_NAME)) {           // announce rover.local so nobody types the IP
      MDNS.addService("http", "tcp", 80);
      Serial.println("Name: http://rover.local");
    } else {
      Serial.println("mDNS failed - use the IP above");
    }
  } else {
    // 2.5.3: say WHY. A scan shows whether the hotspot is even visible to the
    // station radio (it is, if a line ends in MATCH), or whether the join was
    // refused (wrong password / client limit).
    Serial.printf("\nFirst join failed (status %d). Scanning what the radio can see...\n", WiFi.status());
    int found = WiFi.scanNetworks();
    for (int i = 0; i < found; i++) {
      bool match = WiFi.SSID(i) == wifiSSID;
      Serial.printf("  %-24s ch=%2d rssi=%3d%s\n", WiFi.SSID(i).c_str(), WiFi.channel(i), WiFi.RSSI(i),
                    match ? "  <-- MATCH" : "");
    }
    WiFi.scanDelete();
    // One retry, same proven-clean sequence as above (no disconnect(true)!)
    Serial.println("One clean retry...");
    WiFi.disconnect();
    WiFi.begin(wifiSSID, wifiPass);
    int retry = 0;
    while (WiFi.status() != WL_CONNECTED && retry < 20) {   // another 10 s
      delay(500);
      Serial.print(".");
      retry++;
    }
    if (WiFi.status() == WL_CONNECTED) {
      Serial.println("\nWiFi station connected on retry. IP: " + WiFi.localIP().toString());
      WiFi.setSleep(false);
      WiFi.mode(WIFI_AP_STA);
      if (MDNS.begin(MDNS_NAME)) {
        MDNS.addService("http", "tcp", 80);
        Serial.println("Name: http://rover.local");
      } else {
        Serial.println("mDNS failed - use the IP above");
      }
    } else {
      Serial.printf("\nWiFi station connection failed (status %d). Check the hotspot.\n", WiFi.status());
    }
  }
  // WiFi AP and routes (AP mode for local web UI)
  WiFi.mode(WIFI_AP_STA);          // 2.5.2: guarantee dual mode even when the station never joined
  WiFi.softAP(apSSID, apPass);     // web server
  IPAddress apIP = WiFi.softAPIP();
  Serial.print("AP IP: "); Serial.println(apIP);
  server.on("/", HTTP_GET, handleRoot);// complete server/ web ui
  server.on("/startnav", HTTP_GET, handleStartNavigation);//individual buttons
  server.on("/startstop", HTTP_GET, handleStartStopRover);
  server.on("/sensors/data", HTTP_GET, handleSensorsData);
  server.on("/startjev", HTTP_GET, handleStartJev);
  server.on("/jev/cmd", HTTP_POST, handleJevCmd);
  server.on("/id", HTTP_GET, handleId);
  server.onNotFound(notFound);
  const char* headerKeys[] = {"X-Token"};   // WebServer only keeps headers we ask for
  server.collectHeaders(headerKeys, 1);
  if (strlen(roverCmdToken) < 8) Serial.println("WARNING: ROVER_CMD_TOKEN is under 8 characters - Jev commands will be refused");
  server.begin();
  Serial.println("HTTP server started");
}
// ---------- loop heartbeat (2.4.1: catch the freeze) ----------
// One letter per loop stage, rate-limited to 2 s: H after server.handleClient(),
// M after mpu.update(), D after sampleDistance(), J after jevLoop().
// A full BEAT line (incl. free heap) every 10 s. When the web server freezes:
// the letters stop in order, and the MISSING letter names the hung stage.
void beat(char stage) {
  static const char stages[] = {'H', 'M', 'D', 'J'};
  static unsigned long lastMs[4] = {0, 0, 0, 0};
  for (int i = 0; i < 4; i++) {
    if (stages[i] == stage && millis() - lastMs[i] >= 2000) {
      lastMs[i] = millis();
      Serial.print(stage);
    }
  }
}
unsigned long lastBeatFullMs = 0;
void beatFull() {
  if (millis() - lastBeatFullMs >= 10000) {
    lastBeatFullMs = millis();
    Serial.printf("BEAT ms=%lu heap=%lu jev=%d\n", millis(), (unsigned long)ESP.getFreeHeap(), jevEnabled ? 1 : 0);
  }
}
void loop() {
  server.handleClient();
  beat('H');
  // 1. Refresh IMU data
  mpu.update();
  beat('M');
  sampleDistance();   // keeps distance_cm fresh for telemetry and the Jev vetoes
  beat('D');
  refreshSlowSensors();   // bmp + dht on a 2 s timer, so /sensors/data never blocks

  // 2. LDR LED logic
  int ldrState = digitalRead(LDR_PIN);
  digitalWrite(LDR_LED, (ldrState == HIGH) ? HIGH : LOW);

  // 3. MPU Data Capture (For Telemetry Only) - pitch/roll from the accelerometer
  refreshAngles();
  float p = pitchDeg;
  float r = rollDeg;
  float curX = mpu.getAccX();
  float curY = mpu.getAccY();
  float curZ = mpu.getAccZ();
  
  // Update internal variables for telemetry 
   /*The Science: On a perfectly flat, still surface, the Z-axis (pointing up) always reads 1.0 G because of Earth's gravity.
The Logic: If the rover is on a smooth floor, the reading is 1.0. So, $1.0 - 1.0 = 0$.
The Result: The vibrationScore stays at 0. */
vibrationScore = abs(curZ - 1.0);    
lastAccX = curX; lastAccY = curY;

  // Detect Events for logging (Doesn't affect movement)
  expireOldEvent();   // a stale "Tilt Warning" must not outlive its moment
  if (abs(p) > ROLLOVER_LIMIT || abs(r) > ROLLOVER_LIMIT) markEvent("Tilt Warning");  // abs means distance from zero
  else if (abs(curX - lastAccX) > IMPACT_THRESHOLD) markEvent("Impact Detected");

  // Jev Auto: finish moves on time, watchdog, reflexes (never blocks)
  if (jevEnabled) {
    jevLoop();
    beat('J');
  }
  beatFull();

  // 4. Autonomous behavior (Simple Ultrasonic Only)
  if (autonomousEnabled) {
    long distance = getDistance(); // main obstacle avoidance logic
    if (distance > 0 && distance < SAFE_DISTANCE_CM) {
      markEvent("Obstacle Avoided");
      stopMotors(); 
      delay(50);
      backward(DEFAULT_SPEED); 
      delay(BACKUP_TIME_MS);
      stopMotors(); 
      delay(50);
      rightTurn(TURN_SPEED); 
      delay(TURN_TIME_MS);
      stopMotors(); 
      delay(50);
    } else {
      forward(DEFAULT_SPEED);
    }
    delay(80);
  }
  // Simple forward override (if button active and not autonomous)
  if (roverMoving && !autonomousEnabled) {
    forward(FORWARD_SPEED);
  }
  // Send data to Supabase periodically if connected
  // OFF by default (SUPABASE_UPLOAD 0): the blocking TLS handshake starved the
  // web server, so /sensors/data and /jev/cmd timed out mid-drive. See PR: camera fix 2.2.0.
  // 2.5.0: compiled out entirely - flipping the #define back on now requires a
  // code change (and should carry a note that TLS handshake costs ~1-3 s frozen loop).
#if SUPABASE_UPLOAD
  if (WiFi.status() == WL_CONNECTED && millis() - lastSendTime >= sendIntervalMs) {
    lastSendTime = millis();
    sendDataToSupabase();
  }
#endif
}
// ---------------- Web UI - Single page ----------------
// 2.5.0: the page used to be copied into a ~12 KB heap String on EVERY page
// load and freed after sending - that alloc/free churn fragments the heap and
// makes mid-response send failures (truncated JSON) increasingly likely until
// the server wedges. Served straight from flash now, zero heap copies.
static const char PAGE[] PROGMEM = R"rawliteral(
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Mars Mission Control</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=JetBrains+Mono:wght@400;600&display=swap');
    :root {
      --mars-red: #ff4d00;
      --bg-dark: #050a14;
      --glass: rgba(255, 255, 255, 0.05);
      --accent: #00d1b2;
      --text: #e0e0e0;
    }
    body {
      margin: 0;
      background: linear-gradient(135deg, #050a14 0%, #1a0a05 100%);
      color: var(--text);
      font-family: 'JetBrains Mono', monospace;
      display: flex;
      justify-content: center;
      min-height: 100vh;
      overflow-x: hidden;
    }
    .container {
      width: 95%;
      max-width: 480px;
      padding: 20px;
    }
    header {
      text-align: center;
      margin-bottom: 25px;
      padding-bottom: 15px;
      border-bottom: 1px solid var(--mars-red);
    }
    h1 {
      font-family: 'Orbitron', sans-serif;
      font-size: 20px;
      color: var(--mars-red);
      letter-spacing: 4px;
      margin: 0;
      text-shadow: 0 0 10px rgba(255, 77, 0, 0.5);
    }
    .badge {
      font-size: 10px;
      background: var(--mars-red);
      color: #000;
      padding: 2px 8px;
      border-radius: 4px;
      font-weight: bold;
      vertical-align: middle;
    }
    .card {
      background: var(--glass);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 20px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
    }
    .btn {
      display: block;
      width: 100%;
      padding: 18px;
      margin-bottom: 15px;
      border: 1px solid rgba(255, 255, 255, 0.2);
      border-radius: 8px;
      font-family: 'Orbitron', sans-serif;
      font-size: 14px;
      font-weight: 700;
      text-transform: uppercase;
      cursor: pointer;
      transition: all 0.3s;
      background: rgba(255, 255, 255, 0.05);
      color: var(--text);
    }
    .btn:active { transform: scale(0.98); }
    .nav-btn.active {
      background: var(--mars-red);
      color: #000;
      border-color: var(--mars-red);
      box-shadow: 0 0 20px rgba(255, 77, 0, 0.4);
    }
    .go-btn.active {
      background: var(--accent);
      color: #000;
      border-color: var(--accent);
      box-shadow: 0 0 20px rgba(0, 209, 178, 0.4);
    }
    .jev-btn.active {
      background: #9b5cff;
      color: #000;
      border-color: #9b5cff;
      box-shadow: 0 0 20px rgba(155, 92, 255, 0.4);
    }
    .sensor-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 15px;
    }
    .sensor-item {
      padding: 12px;
      background: rgba(0,0,0,0.3);
      border-radius: 8px;
      border-left: 2px solid var(--mars-red);
    }
    .label { font-size: 10px; color: #888; text-transform: uppercase; margin-bottom: 5px; }
    .value { font-size: 18px; font-weight: bold; color: #fff; }
    .unit { font-size: 10px; color: #666; margin-left: 4px; }
    .status-panel {
      font-size: 11px;
      display: flex;
      justify-content: space-between;
      margin-top: 10px;
      color: #666;
    }
    .dot {
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #333;
      margin-right: 5px;
    }
    .dot.live { background: #0f0; box-shadow: 0 0 5px #0f0; animation: blink 1s infinite; }
    @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>MARS ROVER <span class="badge">V2.5</span></h1>
    </header>

    <div class="card">
      <button id="navBtn" class="btn nav-btn" onclick="toggleNav()">Initiate Autonomy</button>
      <button id="goBtn" class="btn go-btn" onclick="toggleGo()">Manual Propulsion</button>
      <button id="jevBtn" class="btn jev-btn" onclick="toggleJev()">Jev Auto</button>
      <div class="status-panel">
        <div>COMMS: <span class="dot live"></span>STABLE</div>
        <div>MODE: <span id="modeDisplay">MANUAL</span></div>
      </div>
    </div>

    <div class="card">
      <div style="font-family:'Orbitron'; font-size:12px; color:var(--mars-red); margin-bottom:15px; border-bottom:1px solid rgba(255,77,0,0.2); padding-bottom:5px;">ENVIRONMENTAL TELEMETRY</div>
      <div class="sensor-grid">
        <div class="sensor-item">
          <div class="label">Atmosphere</div>
          <div class="value" id="ldrText">--</div>
        </div>
        <div class="sensor-item">
          <div class="label">Thermal</div>
          <div class="value"><span id="temperature">--</span><span class="unit">°C</span></div>
        </div>
        <div class="sensor-item">
          <div class="label">Moisture</div>
          <div class="value"><span id="humidity">--</span><span class="unit">%</span></div>
        </div>
        <div class="sensor-item">
          <div class="label">Pressure</div>
          <div class="value" id="pressure">--</div>
        </div>
        <div class="sensor-item" style="grid-column: span 2">
          <div class="label">Relative Altitude</div>
          <div class="value"><span id="altitude">--</span><span class="unit">cm</span></div>
        </div>
      </div>
    </div>

    <div class="card">
      <div style="font-family:'Orbitron'; font-size:12px; color:var(--accent); margin-bottom:15px; border-bottom:1px solid rgba(0,209,178,0.2); padding-bottom:5px;">ORIENTATION & STABILITY</div>
      <div class="sensor-grid">
        <div class="sensor-item">
          <div class="label">Pitch</div>
          <div class="value"><span id="pitch">--</span><span class="unit">°</span></div>
        </div>
        <div class="sensor-item">
          <div class="label">Roll</div>
          <div class="value"><span id="roll">--</span><span class="unit">°</span></div>
        </div>
        <div class="sensor-item">
          <div class="label">Obstacle</div>
          <div class="value" id="distance">--</div>
        </div>
        <div class="sensor-item">
          <div class="label">Terrain Vibration</div>
          <div class="value" id="vibeStatus">SMOOTH</div>
        </div>
      </div>
    </div>
  </div>

  <script>
    let navEnabled = false;
    let roverGo = false;

    function send(path){ fetch(path).catch(e=>console.log('Telemetry interruption:',e)); }

    let jevOn = false;

    function toggleNav(){
      navEnabled = !navEnabled;
      jevOn = false;                 // any manual button leaves Jev Auto
      send('/startnav');
      if (navEnabled) roverGo = false;
      updateButtons();
    }

    function toggleGo(){
      if (navEnabled) return;
      send('/startstop');
      if (jevOn) { jevOn = false; roverGo = false; }   // first press just leaves Jev Auto
      else roverGo = !roverGo;
      updateButtons();
    }

    function toggleJev(){
      jevOn = !jevOn;
      send('/startjev');
      if (jevOn) { navEnabled = false; roverGo = false; }
      updateButtons();
    }

    function updateButtons(){
      const nav = document.getElementById('navBtn');
      nav.innerText = navEnabled ? 'Abort Autonomy' : 'Initiate Autonomy';
      nav.classList.toggle('active', navEnabled);
      const go = document.getElementById('goBtn');
      go.innerText = roverGo ? 'Halt Propulsion' : 'Manual Propulsion';
      go.classList.toggle('active', roverGo);
      const jev = document.getElementById('jevBtn');
      jev.innerText = jevOn ? 'Exit Jev Auto' : 'Jev Auto';
      jev.classList.toggle('active', jevOn);
      document.getElementById('modeDisplay').innerText = jevOn ? 'JEV AUTO' : (navEnabled ? 'AUTONOMOUS' : 'MANUAL');
    }

    async function fetchData(){
      try {
        const res = await fetch('/sensors/data');
        const j = await res.json();
        document.getElementById('ldrText').innerText = j.ldrState==1 ? 'NIGHT' : 'DAY';
        document.getElementById('pressure').innerText = j.pressure ? j.pressure.toFixed(1) + ' hPa' : '--';
        document.getElementById('altitude').innerText = j.altitude ? j.altitude.toFixed(0) : '--';
        document.getElementById('temperature').innerText = j.temperature ? j.temperature.toFixed(1) : '--';
        document.getElementById('humidity').innerText = j.humidity ? j.humidity.toFixed(0) : '--';
        document.getElementById('pitch').innerText = j.pitch ? j.pitch.toFixed(1) : '--';
        document.getElementById('roll').innerText = j.roll ? j.roll.toFixed(1) : '--';
        document.getElementById('vibeStatus').innerText = j.vibration > 0.08 ? 'ROUGH' : 'SMOOTH';
        document.getElementById('vibeStatus').style.color = j.vibration > 0.08 ? 'var(--mars-red)' : 'var(--accent)';
        document.getElementById('distance').innerText = j.distance_cm >= 0 ? j.distance_cm + ' cm' : '--';
        if (j.mode) {                      // the rover is the source of truth for the mode
          jevOn = j.mode == 'jev';
          navEnabled = j.mode == 'autonomy';
          if (jevOn || navEnabled) roverGo = false;
          updateButtons();
        }
      } catch(e) {}
    }

    setInterval(fetchData, 800);
    fetchData();
  </script>
</body>
</html>
)rawliteral";
void handleRoot() {
  server.send_P(200, "text/html", PAGE);
}
void handleStartNavigation() {
  if (jevEnabled) setJevMode(false);   // any manual button leaves Jev Auto
  autonomousEnabled = !autonomousEnabled;
  if (!autonomousEnabled) stopMotors();
  roverMoving = false; // reset manual forward when toggling nav
  server.send(200, "text/plain", autonomousEnabled ? "Navigation ON" : "Navigation OFF");
}
void handleStartStopRover() {
  if (jevEnabled) {                    // any manual button leaves Jev Auto
    setJevMode(false);
    server.send(200, "text/plain", "Jev Auto off - rover stopped");
    return;
  }
  if (autonomousEnabled) {
    server.send(200, "text/plain", "Navigation active - ignored");
    return;
  }
  roverMoving = !roverMoving;
  if (!roverMoving) stopMotors();
  server.send(200, "text/plain", roverMoving ? "Rover moving forward" : "Rover stopped");
}
// ---------- cached slow sensors (2.5.0) ----------
// The old /sensors/data did blocking I2C (bmp) + a bit-banged DHT read + ~12
// chained String allocations on EVERY call, at 5 calls/s - a long busy window
// that collided with the laptop's pollers and starved the single-threaded
// WebServer. Now loop() refreshes these every 2 s; the handler only formats.
float cachedPressureHpa = NAN, cachedRelAltitudeCm = NAN, cachedTempC = NAN, cachedHumidityPct = NAN;
bool pressureValid = false, tempValid = false;
unsigned long lastSlowSensorMs = 0;
const unsigned long SLOW_SENSOR_EVERY_MS = 2000;
// 2.5.1: I2C diagnostics - the ground crew needs to SEE the bus state and the
// raw gravity vector, not just pitch/roll conclusions. i2cMpuOk = the last
// handshake with the MPU6050 answered; i2cRecoveries counts auto re-inits.
bool i2cMpuOk = false;
int i2cRecoveries = 0;
const char* fmtPressure() { static char b[16]; snprintf(b, sizeof(b), "%.2f", cachedPressureHpa); return b; }
const char* fmtAltitude() { static char b[16]; snprintf(b, sizeof(b), "%.2f", cachedRelAltitudeCm); return b; }
const char* fmtTemp() { static char b[16]; snprintf(b, sizeof(b), "%.1f", cachedTempC); return b; }
const char* fmtHumidity() { static char b[16]; snprintf(b, sizeof(b), "%.0f", cachedHumidityPct); return b; }
void refreshSlowSensors() {
  if (millis() - lastSlowSensorMs < SLOW_SENSOR_EVERY_MS) return;
  lastSlowSensorMs = millis();
  // I2C health probe + one auto-recovery: if the MPU stops answering, re-init
  // the Wire stub and try again (a bus lock after a motor-glitch recovers here
  // instead of leaving angles frozen and every move refused as tilt).
  Wire.beginTransmission(0x68);
  i2cMpuOk = (Wire.endTransmission() == 0);
  if (!i2cMpuOk) {
    Wire.end();
    delay(2);
    Wire.begin(25, 26);
    Wire.beginTransmission(0x68);
    i2cMpuOk = (Wire.endTransmission() == 0);
    if (i2cMpuOk) i2cRecoveries++;
  }
  if (bmpFound) {
    cachedPressureHpa = bmp.readPressure() / 100.0;
    cachedRelAltitudeCm = (bmp.readAltitude(101325.0) - baselineAltitudeM) * 100.0;
    pressureValid = true;
  }
  float t = dht.readTemperature();
  cachedTempC = t;
  cachedHumidityPct = dht.readHumidity();
  tempValid = !isnan(t) && !isnan(cachedHumidityPct);
}
void handleSensorsData() {  // it actualy sends the readings in the design
  char buf[448];
  snprintf(buf, sizeof(buf),
    "{\"ldrState\":%d,\"pressure\":%s,\"altitude\":%s,\"temperature\":%s,\"humidity\":%s,"
    "\"pitch\":%.1f,\"roll\":%.1f,\"accX\":%.3f,\"accY\":%.3f,\"accZ\":%.3f,"
    "\"i2c_ok\":%d,\"i2c_recov\":%d,\"vibration\":%.3f,\"autonomous\":%d,"
    "\"distance_cm\":%ld,\"mode\":\"%s\",\"last_event\":\"%s\"}",
    digitalRead(LDR_PIN),
    pressureValid ? fmtPressure() : "null",
    pressureValid ? fmtAltitude() : "null",
    tempValid ? fmtTemp() : "null",
    tempValid ? fmtHumidity() : "null",
    pitchDeg, rollDeg,
    mpu.getAccX(), mpu.getAccY(), mpu.getAccZ(),
    i2cMpuOk ? 1 : 0, i2cRecoveries,
    vibrationScore,
    autonomousEnabled ? 1 : 0,
    lastDistanceCm,
    roverMode().c_str(), lastEvent.c_str());
  server.send(200, "application/json", buf);
}
void notFound() { server.send(404, "text/plain", "Not found"); }
// ---------------- Motor helpers ----------------
void forward(int speed) {
  digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, HIGH);
  ledcWrite(ENA, constrain(speed,0,255)); ledcWrite(ENB, constrain(speed,0,255));
}
void backward(int speed) {
  digitalWrite(IN1, LOW); digitalWrite(IN2, HIGH);
  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
  ledcWrite(ENA, constrain(speed,0,255)); ledcWrite(ENB, constrain(speed,0,255));
}
void leftTurn(int speed) {
  digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
  ledcWrite(ENA, constrain(speed,0,255)); ledcWrite(ENB, constrain(speed,0,255));
}
void rightTurn(int speed) {
  digitalWrite(IN1, LOW); digitalWrite(IN2, HIGH);
  digitalWrite(IN3, LOW); digitalWrite(IN4, HIGH);
  ledcWrite(ENA, constrain(speed,0,255)); ledcWrite(ENB, constrain(speed,0,255));
}
void stopMotors() {
  digitalWrite(IN1, LOW); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, LOW);
  ledcWrite(ENA, 0); ledcWrite(ENB, 0);
}
// ---------------- Ultrasonic functions ----------------
long singleUltrasonicReading() {
  digitalWrite(TRIG_PIN, LOW); delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  unsigned long duration = pulseIn(ECHO_PIN, HIGH, 12000UL);  // 12 ms cap (~2 m); the old 30 ms block starved the web server
  if (duration == 0) return -1;
  float distCm = (duration * 0.034f) / 2.0f; //speed of souund in cm/ms 0.034
  return (long)(distCm + 0.5f);
}
long getDistance() {
  long a = singleUltrasonicReading(); delay(6);
  long b = singleUltrasonicReading(); delay(6);
  long c = singleUltrasonicReading();
  return medianOf3(a, b, c);
}
long medianOf3(long a, long b, long c) {
  if (a > b) { long t = a; a = b; b = t; }
  if (b > c) { long t = b; b = c; c = t; }
  if (a > b) { long t = a; a = b; b = t; }
  if (b <= 0) return -1;
  return b;
}
// One reading every DISTANCE_EVERY_MS instead of three in a row, so loop() stays responsive
void sampleDistance() {
  if (millis() - lastDistanceMs < DISTANCE_EVERY_MS) return;
  lastDistanceMs = millis();
  distSamples[distIndex] = singleUltrasonicReading();
  distIndex = (distIndex + 1) % 3;
  lastDistanceCm = medianOf3(distSamples[0], distSamples[1], distSamples[2]);
}
// Function to collect sensors and send to Supabase
void sendDataToSupabase() {
  // Read sensor values
  int ldrState = digitalRead(LDR_PIN);
  float pressureHpa = NAN;
  float relAltitudeCm = NAN;
  if (bmpFound) {
    pressureHpa = bmp.readPressure() / 100.0;
    float absAltM = bmp.readAltitude(101325.0);
    relAltitudeCm = (absAltM - baselineAltitudeM) * 100.0;
  }
  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();
 
  // Build JSON payload for Supabase (matching table columns)
  String payload = "{";
  payload += "\"temperature\":" + (isnan(temperature) ? "null" : String(temperature, 1));
  payload += ",\"humidity\":" + (isnan(humidity) ? "null" : String(humidity, 0));
  payload += ",\"ldr_state\":\"" + String(ldrState == 1 ? "Night" : "Day") + "\"";
  payload += ",\"pressure\":" + (bmpFound ? String(pressureHpa, 2) : "null");
  payload += ",\"altitude\":" + (bmpFound ? String(relAltitudeCm, 2) : "null");
  payload += ",\"pitch\":" + String(pitchDeg, 1);
  payload += ",\"roll\":" + String(rollDeg, 1);
  payload += ",\"vibration\":" + String(vibrationScore, 3);
  payload += ",\"last_event\":\"" + lastEvent + "\"";
  payload += "}";
  
  // Reset last event after sending
  if (lastEvent != "Nominal") lastEvent = "Nominal";
 
  Serial.print("Supabase Payload: "); Serial.println(payload);

  // Supabase REST API endpoint for sensor_readings table
  String url = supabaseUrl + "/rest/v1/sensor_readings";
 
  // Send POST request
  HTTPClient http;
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("apikey", supabaseKey);
  http.addHeader("Authorization", "Bearer " + supabaseKey);
  http.addHeader("Prefer", "return=minimal");
 
  int httpResponseCode = http.POST(payload);
 
  // Debug output
  if (httpResponseCode == 201) {
    Serial.println("Data sent to Supabase successfully!");
  } else if (httpResponseCode > 0) {
    Serial.printf("Supabase response: HTTP %d\n", httpResponseCode);
    String response = http.getString();
    Serial.println("Response: " + response);
  } else {
    Serial.printf("Error sending to Supabase: %d\n", httpResponseCode);
  }
  http.end();
}
// ---------------- Jev Auto (Earth Station) ----------------
// Protocol: docs/EARTH_STATION.md#rover-protocol. Reference implementation: earth_station/sim.py
String roverMode() {
  if (jevEnabled) return "jev";
  if (autonomousEnabled) return "autonomy";
  return "manual";
}
bool isTilted() {
  return abs(pitchDeg) > ROLLOVER_LIMIT || abs(rollDeg) > ROLLOVER_LIMIT;
}
void stopJevMove() {
  stopMotors();
  jevMoving = false;
  jevAction = "stop";
}
void setJevMode(bool on) {
  jevEnabled = on;
  stopJevMove();
  if (on) {
    autonomousEnabled = false;
    roverMoving = false;
    hasLastJevSeq = false;        // forget the last seq when Jev Auto is switched on
    lastJevCmdMs = millis();
  }
  Serial.println(on ? "Jev Auto ON" : "Jev Auto OFF");
}
void handleStartJev() {
  setJevMode(!jevEnabled);
  server.send(200, "text/plain", jevEnabled ? "Jev Auto ON" : "Jev Auto OFF");
}
void handleId() {
  server.send(200, "application/json",
              String("{\"board\":\"rover\",\"firmware\":\"") + FIRMWARE_VERSION + "\"}");
}
// Called every loop() while in Jev Auto
void jevLoop() {
  if (!jevMoving) return;
  if (millis() - lastJevCmdMs > JEV_WATCHDOG_MS) {   // laptop went quiet
    Serial.println("Jev watchdog: no command, stopping");
    stopJevMove();
    return;
  }
  if (millis() - jevMoveStartMs >= jevMoveMs) {      // move finished
    stopJevMove();
    return;
  }
  if (jevAction == "forward" && lastDistanceCm > 0 && lastDistanceCm < JEV_MIN_FORWARD_CM) {
    markEvent("Obstacle Avoided");                  // reflex: something appeared ahead
    stopJevMove();
    return;
  }
  if (isTilted()) {
    markEvent("Tilt Warning");
    stopJevMove();
  }
}
void runJevMove(const String& action, int speed, unsigned long ms) {
  if (action == "forward") forward(speed);
  else if (action == "reverse") backward(speed);
  else if (action == "turn_left") leftTurn(speed);
  else if (action == "turn_right") rightTurn(speed);
  jevAction = action;
  jevMoving = true;
  jevMoveStartMs = millis();
  jevMoveMs = ms;                 // jevLoop() stops the motors when time is up, no delay()
}
// Tiny JSON readers for the fixed /jev/cmd body: {"seq": 1, "action": "forward", "speed": 170, "duration_ms": 300}
int jsonValueStart(const String& body, const char* key) {
  String needle = String("\"") + key + "\"";
  int i = body.indexOf(needle);
  if (i < 0) return -1;
  i = body.indexOf(':', i + needle.length());
  if (i < 0) return -1;
  i++;
  while (i < (int)body.length() && isspace(body[i])) i++;
  return i < (int)body.length() ? i : -1;
}
bool jsonLong(const String& body, const char* key, long& out) {
  int i = jsonValueStart(body, key);
  if (i < 0 || (body[i] != '-' && !isdigit(body[i]))) return false;
  out = body.substring(i).toInt();
  return true;
}
String jsonString(const String& body, const char* key) {
  int i = jsonValueStart(body, key);
  if (i < 0 || body[i] != '"') return "";
  int end = body.indexOf('"', i + 1);
  return end < 0 ? "" : body.substring(i + 1, end);
}
void sendJevReply(const String& seqText, bool ok, const char* field, const String& value) {
  server.send(200, "application/json",
              String("{\"ok\":") + (ok ? "true" : "false") + ",\"seq\":" + seqText +
              ",\"" + field + "\":\"" + value + "\"}");
}
void handleJevCmd() {
  if (strlen(roverCmdToken) < 8 || server.header("X-Token") != roverCmdToken) {
    server.send(401, "application/json", "{\"ok\":false,\"refused\":\"bad_token\"}");
    return;
  }
  String body = server.arg("plain");
  if (body.length() == 0) {
    server.send(400, "application/json", "{\"ok\":false,\"refused\":\"bad_json\"}");
    return;
  }
  lastJevCmdMs = millis();        // feed the watchdog
  long seq = 0;
  bool hasSeq = jsonLong(body, "seq", seq);
  String seqText = hasSeq ? String(seq) : "null";
  String action = jsonString(body, "action");

  if (!jevEnabled) { sendJevReply(seqText, false, "refused", "not_in_jev_mode"); return; }
  if (action != "forward" && action != "turn_left" && action != "turn_right" &&
      action != "reverse" && action != "stop") {
    sendJevReply(seqText, false, "refused", "unknown_action");
    return;
  }
  if (hasSeq && hasLastJevSeq && seq == lastJevSeq) {   // a retry of the last command
    sendJevReply(seqText, true, "executed", "duplicate_ignored");
    return;
  }
  if (hasSeq) { lastJevSeq = seq; hasLastJevSeq = true; }

  long speed = 0, ms = 0;
  jsonLong(body, "speed", speed);
  jsonLong(body, "duration_ms", ms);
  speed = constrain(speed, 0, 255);
  ms = constrain(ms, 0, (long)JEV_MAX_MOVE_MS);

  if (action == "stop") {
    stopJevMove();
    sendJevReply(seqText, true, "executed", "stop");
    return;
  }
  if (isTilted()) {                                      // veto: tipping over
    markEvent("Tilt Warning");
    stopJevMove();
    sendJevReply(seqText, false, "refused", "tilt");
    return;
  }
  if (action == "forward" && lastDistanceCm > 0 && lastDistanceCm < JEV_MIN_FORWARD_CM) {
    markEvent("Obstacle Avoided");                       // veto: too close ahead
    stopJevMove();
    sendJevReply(seqText, false, "refused", "obstacle_too_close");
    return;
  }
  runJevMove(action, speed, ms);
  sendJevReply(seqText, true, "executed", action);
}
