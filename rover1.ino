/*
  ESP32 Rover — Complete sketch
  - WiFi AP + web UI (manual + autonomous)
  - Ultrasonic obstacle avoidance + IR edge detection
  - LDR status
  - BMP280 pressure (hPa) and relative altitude (cm, zero at startup)
  - BMP280 wiring: VCC->3.3V, GND->GND, SDA->GPIO25, SCL->GPIO26
  - SDO/CSB left unwired (code tries 0x76 then 0x77)
  - Front LED control pin kept but LED is currently disconnected
  - DHT11 temperature (°C) and humidity (%) using pin 27
  Hammad: This is drop-in ready.
  
  NEW: Send sensor data to n8n webhook every 10 seconds via POST.
*/
#include <Wire.h>
#include <WiFi.h>
#include <WebServer.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BMP280.h>
#include <DHT.h>
#include <HTTPClient.h>  // NEW: For sending HTTP POST to n8n
// ---------- WiFi Station (for internet) ---------- // NEW
const char* wifiSSID = "REDACTED_SSID";      // Replace with your WiFi name
const char* wifiPass = "REDACTED_WIFI_PASS"; // Replace with your WiFi password
// ---------- Supabase Configuration ----------
const String supabaseUrl = "https://your-project-ref.supabase.co";
const String supabaseKey = "REDACTED_SUPABASE_ANON_KEY";
// ---------- Data Send Interval ----------
unsigned long lastSendTime = 0;
const unsigned long sendIntervalMs = 5000;  // Send every 5 seconds
// ---------- WiFi AP ----------
const char* apSSID = "ESP32-Car-AP";
const char* apPass = "REDACTED_AP_PASS";
WebServer server(80);
// ---------- Motor Pins ----------
const int ENA = 23;
const int IN1 = 22;
const int IN2 = 21;
const int ENB = 19;
const int IN3 = 18;
const int IN4 = 5;
// PWM (ledc) channels
const int PWM_FREQ = 5000;
const int PWM_RES = 8; // 0-255
const int CH_A = 0;
const int CH_B = 1;
// ---------- Ultrasonic Pins ----------
const int TRIG_PIN = 32;
const int ECHO_PIN = 35;
// ---------- IR Edge Detection Pins ----------
const int IR_LEFT = 17;
const int IR_RIGHT = 16;
// ---------- LDR Pins ----------
const int LDR_PIN = 33; // digital OUT from LDR module
const int LDR_LED = 4; // indicator GPIO (LED is disconnected for now)
// ---------- DHT11 ----------
const int DHT_PIN = 27;
DHT dht(DHT_PIN, DHT11);
// ---------- BMP280 ----------
Adafruit_BMP280 bmp;
bool bmpFound = false;
float bmpBaselinePressure = 101325.0; // Pa, informational
float baselineAltitudeM = 0.0; // meters vs sea level captured at startup
// ---------- Behavior ----------
volatile int currentSpeed = 150; // 0-255
volatile bool autonomousEnabled = false;
const int SAFE_DISTANCE_CM = 40;
const int DEFAULT_SPEED = 150;
const int TURN_SPEED = 220;
const int BACKUP_TIME_MS = 400;
const int TURN_TIME_MS = 600;
// ---------- Forward declarations ----------
void handleRoot();
void handleCmd();
void handleSpeed();
void handleAutonomous();
void handleSensorsPage();
void handleSensorsData();
void notFound();
long getDistance();
long singleUltrasonicReading();
void forward(int speed);
void backward(int speed);
void leftTurn(int speed);
void rightTurn(int speed);
void stopMotors();
void sendDataToSupabase();  // Function to send sensor data to Supabase
void setup() {
  Serial.begin(115200);
  delay(100);
  // Motor pins
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  // PWM setup
  ledcSetup(CH_A, PWM_FREQ, PWM_RES);
  ledcSetup(CH_B, PWM_FREQ, PWM_RES);
  ledcAttachPin(ENA, CH_A);
  ledcAttachPin(ENB, CH_B);
  // Sensors pins
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(IR_LEFT, INPUT);
  pinMode(IR_RIGHT, INPUT);
  pinMode(LDR_PIN, INPUT);
  pinMode(LDR_LED, OUTPUT);
  digitalWrite(LDR_LED, LOW);
  digitalWrite(TRIG_PIN, LOW);
  stopMotors();
  // DHT11
  dht.begin();
  // I2C on GPIO25 (SDA) and GPIO26 (SCL)
  Wire.begin(25, 26);
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
  WiFi.mode(WIFI_AP_STA);
  // NEW: Connect to WiFi (station mode) for internet
  WiFi.begin(wifiSSID, wifiPass);
  Serial.print("Connecting to WiFi station...");
  int wifiAttempts = 0;
  while (WiFi.status() != WL_CONNECTED && wifiAttempts < 20) {
    delay(500);
    Serial.print(".");
    wifiAttempts++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi station connected. IP: " + WiFi.localIP().toString());
  } else {
    Serial.println("\nWiFi station connection failed. Data sending disabled.");
  }
  // WiFi AP and routes (AP mode for local web UI)
  WiFi.softAP(apSSID, apPass);
  IPAddress apIP = WiFi.softAPIP();
  Serial.print("AP IP: "); Serial.println(apIP);
  server.on("/", HTTP_GET, handleRoot);
  server.on("/cmd", HTTP_GET, handleCmd);
  server.on("/speed", HTTP_GET, handleSpeed);
  server.on("/autonomous", HTTP_GET, handleAutonomous);
  server.on("/sensors", HTTP_GET, handleSensorsPage);
  server.on("/sensors/data", HTTP_GET, handleSensorsData);
  server.onNotFound(notFound);
  server.begin();
  Serial.println("HTTP server started");
}
void loop() {
  server.handleClient();
  // LDR LED (indicator; LED is disconnected but keep logic)
  int ldrState = digitalRead(LDR_PIN);
  digitalWrite(LDR_LED, (ldrState == HIGH) ? HIGH : LOW);
  // Autonomous behavior
  if (autonomousEnabled) {
    int leftEdge = digitalRead(IR_LEFT);
    int rightEdge = digitalRead(IR_RIGHT);
    if (leftEdge == HIGH && rightEdge == LOW) {
      stopMotors(); delay(50);
      rightTurn(TURN_SPEED); delay(TURN_TIME_MS);
      stopMotors(); delay(50); return;
    } else if (rightEdge == HIGH && leftEdge == LOW) {
      stopMotors(); delay(50);
      leftTurn(TURN_SPEED); delay(TURN_TIME_MS);
      stopMotors(); delay(50); return;
    } else if (leftEdge == HIGH && rightEdge == HIGH) {
      stopMotors(); delay(50);
      backward(DEFAULT_SPEED); delay(BACKUP_TIME_MS);
      stopMotors(); delay(50); return;
    }
    long distance = getDistance();
    if (distance > 0 && distance < SAFE_DISTANCE_CM) {
      stopMotors(); delay(50);
      backward(DEFAULT_SPEED); delay(BACKUP_TIME_MS);
      stopMotors(); delay(50);
      rightTurn(TURN_SPEED); delay(TURN_TIME_MS);
      stopMotors(); delay(50);
    } else {
      forward(DEFAULT_SPEED);
    }
    delay(80);
  }
  // Send data to Supabase periodically if connected
  if (WiFi.status() == WL_CONNECTED && millis() - lastSendTime >= sendIntervalMs) {
    lastSendTime = millis();
    sendDataToSupabase();
  }
}
// ---------------- Web UI handlers ----------------
void handleRoot() {
  // Mobile-friendly control UI
  String page = R"rawliteral(
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ESP32 Car</title>
<style>
  :root{--bg:#0f1724;--card:#0b1220;--accent:#00d1b2;--muted:#9aa6b2}
  html,body{height:100%;margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial}
  body{background:linear-gradient(180deg,#071021 0%,#071827 100%);color:#fff;display:flex;align-items:center;justify-content:center;padding:12px}
  .wrap{width:100%;max-width:420px;background:linear-gradient(180deg,rgba(255,255,255,0.02),rgba(255,255,255,0.01));border-radius:14px;padding:14px;box-shadow:0 6px 24px rgba(2,6,23,0.6)}
  .row{display:flex;gap:10px;align-items:center;justify-content:center;margin-bottom:12px}
  .big{height:120px}
  .btn{width:72px;height:72px;border-radius:12px;background:linear-gradient(180deg,#0b2a2a,#042022);display:flex;align-items:center;justify-content:center;touch-action:none;user-select:none}
  .btn:active{transform:scale(0.98)}
  .tri-up{width:0;height:0;border-left:16px solid transparent;border-right:16px solid transparent;border-bottom:24px solid var(--accent)}
  .tri-down{width:0;height:0;border-left:16px solid transparent;border-right:16px solid transparent;border-top:24px solid var(--accent)}
  .tri-left{width:0;height:0;border-top:16px solid transparent;border-bottom:16px solid transparent;border-right:24px solid var(--accent)}
  .tri-right{width:0;height:0;border-top:16px solid transparent;border-bottom:16px solid transparent;border-left:24px solid var(--accent)}
  .small{width:56px;height:56px;border-radius:10px;background:#071a1a;display:flex;align-items:center;justify-content:center}
  .speed{width:100%;display:flex;flex-direction:column;gap:6px}
  .slider{width:100%}
  .label{font-size:13px;color:var(--muted);display:flex;justify-content:space-between}
  .toggle{display:flex;gap:8px;align-items:center;justify-content:center}
  .autobtn{padding:8px 12px;border-radius:10px;background:#072a2a;color:#fff;border:1px solid rgba(255,255,255,0.03)}
  .sensorsBtn{padding:8px 12px;border-radius:10px;background:#0a2540;color:#fff;border:1px solid rgba(255,255,255,0.03)}
  .status{font-size:12px;color:var(--muted);text-align:center;margin-top:6px}
  @media (max-width:420px){ .btn{width:64px;height:64px} .big{height:100px} }
</style>
</head>
<body>
  <div class="wrap">
    <div class="row big">
      <div class="btn" id="btn-forward" ontouchstart="startCmd('forward')" ontouchend="stopCmd()" onmousedown="startCmd('forward')" onmouseup="stopCmd()" onmouseleave="stopCmd()">
        <div class="tri-up"></div>
      </div>
    </div>
    <div class="row">
      <div class="btn" id="btn-left" ontouchstart="startCmd('left')" ontouchend="stopCmd()" onmousedown="startCmd('left')" onmouseup="stopCmd()" onmouseleave="stopCmd()">
        <div class="tri-left"></div>
      </div>
      <div class="btn small" id="btn-stop" ontouchstart="startCmd('stop')" ontouchend="stopCmd()" onmousedown="startCmd('stop')" onmouseup="stopCmd()" onmouseleave="stopCmd()">
        <div style="width:0;height:0;border-left:8px solid transparent;border-right:8px solid transparent;border-bottom:12px solid #ff6b6b;transform:rotate(180deg)"></div>
      </div>
      <div class="btn" id="btn-right" ontouchstart="startCmd('right')" ontouchend="stopCmd()" onmousedown="startCmd('right')" onmouseup="stopCmd()" onmouseleave="stopCmd()">
        <div class="tri-right"></div>
      </div>
    </div>
    <div class="row">
      <div class="btn" id="btn-back" ontouchstart="startCmd('backward')" ontouchend="stopCmd()" onmousedown="startCmd('backward')" onmouseup="stopCmd()" onmouseleave="stopCmd()">
        <div class="tri-down"></div>
      </div>
    </div>
    <div class="speed">
      <div class="label"><span>Speed</span><span id="speedVal">)rawliteral";
  page += String(currentSpeed);
  page += R"rawliteral(</span></div>
      <input id="speed" class="slider" type="range" min="0" max="255" value=")rawliteral";
  page += String(currentSpeed);
  page += R"rawliteral(" oninput="updateSpeed(this.value)">
    </div>
    <div class="row toggle">
      <button id="autoBtn" class="autobtn" onclick="toggleAuto()">Autonomous</button>
      <button id="sensorsBtn" class="sensorsBtn" onclick="openSensors()">Sensors</button>
    </div>
    <div class="status" id="status">Mode: Manual</div>
  </div>
<script>
  let auto = false;
  function send(path){ fetch(path).catch(e=>console.log('err',e)); }
  function startCmd(action){
    if(auto) return;
    send('/cmd?act='+action);
  }
  function stopCmd(){
    if(auto) return;
    send('/cmd?act=stop');
  }
  function updateSpeed(v){
    document.getElementById('speedVal').innerText = v;
    send('/speed?v='+v);
  }
  function toggleAuto(){
    auto = !auto;
    send('/autonomous?on='+(auto?'1':'0'));
    document.getElementById('status').innerText = 'Mode: '+(auto?'Autonomous':'Manual');
    document.getElementById('autoBtn').style.background = auto ? '#044' : '#072a2a';
  }
  function openSensors(){ window.location.href = '/sensors'; }
  window.addEventListener('pagehide', stopCmd);
  window.addEventListener('beforeunload', stopCmd);
</script>
</body>
</html>
)rawliteral";
  server.send(200, "text/html", page);
}
void handleCmd() {
  if (autonomousEnabled) { server.send(200, "text/plain", "autonomous"); return; }
  String act = server.arg("act"); act.toLowerCase();
  if (act == "forward") { forward(currentSpeed); server.send(200, "text/plain", "ok"); return; }
  if (act == "backward") { backward(currentSpeed); server.send(200, "text/plain", "ok"); return; }
  if (act == "left") { leftTurn(currentSpeed); server.send(200, "text/plain", "ok"); return; }
  if (act == "right") { rightTurn(currentSpeed);server.send(200, "text/plain", "ok"); return; }
  if (act == "stop") { stopMotors(); server.send(200, "text/plain", "ok"); return; }
  server.send(400, "text/plain", "bad");
}
void handleSpeed() {
  String v = server.arg("v");
  if (v.length() == 0) { server.send(400, "text/plain", "no value"); return; }
  int val = constrain(v.toInt(), 0, 255);
  currentSpeed = val;
  server.send(200, "text/plain", "ok");
}
void handleAutonomous() {
  String on = server.arg("on");
  autonomousEnabled = (on == "1");
  stopMotors();
  server.send(200, "text/plain", autonomousEnabled ? "autonomous on" : "autonomous off");
}
void handleSensorsPage() {
  String page = R"rawliteral(
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sensors</title>
<style>
  body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;margin:0;background:#071827;color:#fff;display:flex;align-items:center;justify-content:center;padding:12px}
  .card{width:100%;max-width:420px;background:#0b1220;border-radius:12px;padding:14px;box-shadow:0 6px 20px rgba(0,0,0,0.6)}
  h2{margin:0 0 10px 0;font-size:18px;color:#00d1b2}
  .row{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.06)}
  .label{color:#9aa6b2}
  .value{font-weight:600}
  .back{margin-top:12px;padding:8px;border-radius:8px;background:#072a2a;color:#fff;border:none;width:100%}
  .status-dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:8px;vertical-align:middle}
</style>
</head>
<body>
  <div class="card">
    <h2>Sensor Readings</h2>
    <div class="row">
      <div class="label">LDR (Day/Night)</div>
      <div><span id="ldrDot" class="status-dot" style="background:#888"></span><span id="ldrText" class="value">--</span></div>
    </div>
    <div class="row">
      <div class="label">Pressure (hPa)</div>
      <div class="value" id="pressure">--</div>
    </div>
    <div class="row">
      <div class="label">Altitude (cm)</div>
      <div class="value" id="altitude">--</div>
    </div>
    <div class="row">
      <div class="label">Temperature (°C)</div>
      <div class="value" id="temperature">--</div>
    </div>
    <div class="row">
      <div class="label">Humidity (%)</div>
      <div class="value" id="humidity">--</div>
    </div>
    <div class="row">
      <div class="label">Autonomous</div>
      <div class="value" id="autoState">--</div>
    </div>
    <button class="back" onclick="goBack()">Back</button>
  </div>
<script>
  function goBack(){ window.location.href = '/'; }
  async function fetchData(){
    try {
      const res = await fetch('/sensors/data');
      if (!res.ok) throw new Error('no data');
      const j = await res.json();
      document.getElementById('ldrText').innerText = j.ldrState==1 ? 'Night' : 'Day';
      document.getElementById('pressure').innerText = (j.pressure !== null) ? j.pressure.toFixed(2) : '--';
      document.getElementById('altitude').innerText = (j.altitude !== null) ? j.altitude.toFixed(0) : '--';
      document.getElementById('temperature').innerText = (j.temperature !== null) ? j.temperature.toFixed(1) : '--';
      document.getElementById('humidity').innerText = (j.humidity !== null) ? j.humidity.toFixed(0) : '--';
      document.getElementById('autoState').innerText = j.autonomous ? 'On' : 'Off';
      const dot = document.getElementById('ldrDot');
      dot.style.background = (j.ldrState==1) ? '#ffd700' : '#4caf50';
    } catch(e) { console.log('err', e); }
  }
  setInterval(fetchData, 600);
  fetchData();
</script>
</body>
</html>
)rawliteral";
  server.send(200, "text/html", page);
}
void handleSensorsData() {
  int ldrState = digitalRead(LDR_PIN);
  float pressureHpa = NAN;
  float relAltitudeCm = NAN;
  if (bmpFound) {
    // Pressure in hPa (Pa / 100)
    pressureHpa = bmp.readPressure() / 100.0;
    // Absolute altitude vs sea level (m), then subtract baseline; convert to cm
    float absAltM = bmp.readAltitude(101325.0);
    relAltitudeCm = (absAltM - baselineAltitudeM) * 100.0;
  }
  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();
  String payload = "{";
  payload += "\"ldrState\":" + String(ldrState);
  payload += ",\"pressure\":" + (bmpFound ? String(pressureHpa, 2) : "null");
  payload += ",\"altitude\":" + (bmpFound ? String(relAltitudeCm, 2) : "null");
  payload += ",\"temperature\":" + (isnan(temperature) ? "null" : String(temperature, 1));
  payload += ",\"humidity\":" + (isnan(humidity) ? "null" : String(humidity, 0));
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
  float distCm = (duration * 0.034f) / 2.0f;
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
  payload += "}";
  
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
