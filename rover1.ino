
#include <Wire.h>
#include <WiFi.h>
#include <WebServer.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BMP280.h>
#include <DHT.h>
#include <HTTPClient.h> 
#include <MPU6050_tockn.h> // NEW: IMU Library
// ---------- WiFi Station (for internet) ---------- // NEW
const char* wifiSSID = "REDACTED_SSID"; // Replace with your WiFi name
const char* wifiPass = "REDACTED_WIFI_PASS"; // Replace with your WiFi password
// ---------- Supabase Configuration ----------
const String supabaseUrl = "https://your-project-ref.supabase.co";
const String supabaseKey = "REDACTED_SUPABASE_ANON_KEY";
// ---------- Data Send Interval ----------
unsigned long lastSendTime = 0;
const unsigned long sendIntervalMs = 5000; // Send every 5 seconds
// ---------- WiFi AP ----------
const char* apSSID = "ESP32-Car-AP";
const char* apPass = "REDACTED_AP_PASS";
WebServer server(80);                   // class/object/port 80 is standard path for http traffic
// ---------- Motor Pins ----------
const int ENA = 23;
const int IN1 = 22;
const int IN2 = 21;
const int ENB = 19;
const int IN3 = 18;
const int IN4 = 5;
// PWM (ledc) channels
const int PWM_FREQ = 5000;      // pulse 5000 times per second 
const int PWM_RES = 8; // 0-255  --> 256 levels of speed
const int CH_A = 0;        // used in ledcstup 
const int CH_B = 1;        // channels (2 out of 15) for speed control 
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
void setup() {
  Serial.begin(115200);
  delay(100);
  // Motor pins
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  // PWM setup
  ledcSetup(CH_A, PWM_FREQ, PWM_RES);   //  settings for virtual wires
  ledcSetup(CH_B, PWM_FREQ, PWM_RES);
  ledcAttachPin(ENA, CH_A);            // connecting virtual wire/chanels to physical pins
  ledcAttachPin(ENB, CH_B);
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
  WiFi.mode(WIFI_AP_STA);         // key word for ap + station mode 
  // NEW: Connect to WiFi (station mode) for internet
  WiFi.begin(wifiSSID, wifiPass);
  Serial.print("Connecting to WiFi station...");
  int wifiAttempts = 0;
  while (WiFi.status() != WL_CONNECTED && wifiAttempts < 20) { // this loop tries 20 times to reconect if connection fails
    delay(500);
    Serial.print(".");
    wifiAttempts++;
  }
  if (WiFi.status() == WL_CONNECTED) {    // checks if esp is connected to wifi 
    Serial.println("\nWiFi station connected. IP: " + WiFi.localIP().toString());  // print ip
  } else {
    Serial.println("\nWiFi station connection failed. Data sending disabled.");
  }
  // WiFi AP and routes (AP mode for local web UI)
  WiFi.softAP(apSSID, apPass);     // web server
  IPAddress apIP = WiFi.softAPIP();
  Serial.print("AP IP: "); Serial.println(apIP);
  server.on("/", HTTP_GET, handleRoot);// complete server/ web ui
  server.on("/startnav", HTTP_GET, handleStartNavigation);//individual buttons
  server.on("/startstop", HTTP_GET, handleStartStopRover);
  server.on("/sensors/data", HTTP_GET, handleSensorsData);
  server.onNotFound(notFound);
  server.begin();
  Serial.println("HTTP server started");
}
void loop() {
  server.handleClient();
  // 1. Refresh IMU data
  mpu.update();

  // 2. LDR LED logic
  int ldrState = digitalRead(LDR_PIN);
  digitalWrite(LDR_LED, (ldrState == HIGH) ? HIGH : LOW);

  // 3. MPU Data Capture (For Telemetry Only)
  float p = mpu.getAngleX();
  float r = mpu.getAngleY();
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
  if (abs(p) > ROLLOVER_LIMIT || abs(r) > ROLLOVER_LIMIT) lastEvent = "Tilt Warning";  // abs means distance from zero
  else if (abs(curX - lastAccX) > IMPACT_THRESHOLD) lastEvent = "Impact Detected";

  // 4. Autonomous behavior (Simple Ultrasonic Only)
  if (autonomousEnabled) {
    long distance = getDistance(); // main obstacle avoidance logic
    if (distance > 0 && distance < SAFE_DISTANCE_CM) {
      lastEvent = "Obstacle Avoided";
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
  // send data every 5s without using delay 
  // main character -> milis function -> like a stopwatch
  if (WiFi.status() == WL_CONNECTED && millis() - lastSendTime >= sendIntervalMs) {
    lastSendTime = millis();
    sendDataToSupabase();
  }
}
// ---------------- Web UI - Single page ----------------
void handleRoot() {
  String page = R"rawliteral(
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
      <h1>MARS ROVER <span class="badge">V2.0</span></h1>
    </header>

    <div class="card">
      <button id="navBtn" class="btn nav-btn" onclick="toggleNav()">Initiate Autonomy</button>
      <button id="goBtn" class="btn go-btn" onclick="toggleGo()">Manual Propulsion</button>
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
        <div class="sensor-item" style="grid-column: span 2">
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

    function toggleNav(){
      navEnabled = !navEnabled;
      send('/startnav');
      document.getElementById('navBtn').innerText = navEnabled ? 'Abort Autonomy' : 'Initiate Autonomy';
      document.getElementById('navBtn').classList.toggle('active', navEnabled);
      document.getElementById('modeDisplay').innerText = navEnabled ? 'AUTONOMOUS' : 'MANUAL';
      if (navEnabled) roverGo = false; 
      updateGoButton();
    }

    function toggleGo(){
      if (navEnabled) return;
      roverGo = !roverGo;
      send('/startstop');
      updateGoButton();
    }

    function updateGoButton(){
      const btn = document.getElementById('goBtn');
      btn.innerText = roverGo ? 'Halt Propulsion' : 'Manual Propulsion';
      btn.classList.toggle('active', roverGo);
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
      } catch(e) {}
    }

    setInterval(fetchData, 800);
    fetchData();
  </script>
</body>
</html>
)rawliteral";
  server.send(200, "text/html", page);
}
void handleStartNavigation() {
  autonomousEnabled = !autonomousEnabled;
  if (!autonomousEnabled) stopMotors();
  roverMoving = false; // reset manual forward when toggling nav
  server.send(200, "text/plain", autonomousEnabled ? "Navigation ON" : "Navigation OFF");
}
void handleStartStopRover() {
  if (autonomousEnabled) {
    server.send(200, "text/plain", "Navigation active - ignored");
    return;
  }
  roverMoving = !roverMoving;
  if (!roverMoving) stopMotors();
  server.send(200, "text/plain", roverMoving ? "Rover moving forward" : "Rover stopped");
}
void handleSensorsData() {  // it actualy sends the readings in the design
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
  String payload = "{";
  payload += "\"ldrState\":" + String(ldrState);
  payload += ",\"pressure\":" + (bmpFound ? String(pressureHpa, 2) : "null"); // 2 decimal places 
  payload += ",\"altitude\":" + (bmpFound ? String(relAltitudeCm, 2) : "null");
  payload += ",\"temperature\":" + (isnan(temperature) ? "null" : String(temperature, 1)); // isnan() is a special shorthand in programming that stands for "is Not a Number."
  payload += ",\"humidity\":" + (isnan(humidity) ? "null" : String(humidity, 0));
  payload += ",\"pitch\":" + String(mpu.getAngleX(), 1);
  payload += ",\"roll\":" + String(mpu.getAngleY(), 1);
  payload += ",\"vibration\":" + String(vibrationScore, 3);
  payload += ",\"autonomous\":" + String(autonomousEnabled ? 1 : 0);
  payload += "}";
  server.send(200, "application/json", payload);
}
void notFound() { server.send(404, "text/plain", "Not found"); }
// ---------------- Motor helpers ----------------
void forward(int speed) {
  digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, HIGH);
  ledcWrite(CH_A, constrain(speed,0,255)); ledcWrite(CH_B, constrain(speed,0,255));
}
void backward(int speed) {
  digitalWrite(IN1, LOW); digitalWrite(IN2, HIGH);
  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
  ledcWrite(CH_A, constrain(speed,0,255)); ledcWrite(CH_B, constrain(speed,0,255));
}
void leftTurn(int speed) {
  digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
  ledcWrite(CH_A, constrain(speed,0,255)); ledcWrite(CH_B, constrain(speed,0,255));
}
void rightTurn(int speed) {
  digitalWrite(IN1, LOW); digitalWrite(IN2, HIGH);
  digitalWrite(IN3, LOW); digitalWrite(IN4, HIGH);
  ledcWrite(CH_A, constrain(speed,0,255)); ledcWrite(CH_B, constrain(speed,0,255));
}
void stopMotors() {
  digitalWrite(IN1, LOW); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, LOW);
  ledcWrite(CH_A, 0); ledcWrite(CH_B, 0);
}
// ---------------- Ultrasonic functions ----------------
long singleUltrasonicReading() {
  digitalWrite(TRIG_PIN, LOW); delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  unsigned long duration = pulseIn(ECHO_PIN, HIGH, 30000UL);
  if (duration == 0) return -1;
  float distCm = (duration * 0.034f) / 2.0f; //speed of souund in cm/ms 0.034
  return (long)(distCm + 0.5f);
}
long getDistance() {
  long a = singleUltrasonicReading(); delay(6);
  long b = singleUltrasonicReading(); delay(6);
  long c = singleUltrasonicReading();
  // median of three
  if (a > b) { long t = a; a = b; b = t; }
  if (b > c) { long t = b; b = c; c = t; }
  if (a > b) { long t = a; a = b; b = t; }
  if (b <= 0) return -1;
  return b;
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
  payload += ",\"pitch\":" + String(mpu.getAngleX(), 1);
  payload += ",\"roll\":" + String(mpu.getAngleY(), 1);
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
