#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <esp_camera.h>
#include <esp_timer.h>
#include <esp_http_server.h>
#include <HTTPClient.h>
#include <time.h>

/* ================= WIFI ================= */
const char* ssid_sta = "REDACTED_SSID";
const char* password_sta = "REDACTED_WIFI_PASS";

const char* ssid_ap = "ESP32_CAM_MARS";
const char* password_ap = "REDACTED_AP_PASS";

/* ================= SUPABASE CONFIG ================= */
const String supabaseUrl = "https://your-project-ref.supabase.co";
const String supabaseKey = "REDACTED_SUPABASE_ANON_KEY";
const String bucketName = "rover_images";

/* ================= HARDWARE ================= */
#define LED_PIN 4
#define CAMERA_MODEL_AI_THINKER

#if defined(CAMERA_MODEL_AI_THINKER)
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22
#endif

/* ================= GLOBALS ================= */
httpd_handle_t server = NULL;
esp_timer_handle_t capture_timer;
volatile bool capture_flag = false;

uint8_t* jpg_buffer = NULL;
size_t jpg_buffer_len = 0;

unsigned long imageCounter = 0;

/* ================= CLEAN MOBILE UI ================= */
const char* html_page = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mars Rover Camera</title>
<style>
body { margin: 0; background: linear-gradient(#2b0000, #0a0000); font-family: Arial, Helvetica, sans-serif; color: #ffffff; }
.header { text-align: center; padding: 14px; font-size: 16px; letter-spacing: 1px; background: rgba(0,0,0,0.5); }
.card { margin: 14px; padding: 10px; background: rgba(255,255,255,0.05); border-radius: 16px; box-shadow: 0 0 25px rgba(255,80,0,0.25); }
img { width: 100%; border-radius: 12px; }
.status { display: flex; justify-content: space-between; font-size: 12px; opacity: 0.8; margin-top: 8px; }
.footer { text-align: center; font-size: 11px; opacity: 0.6; margin-bottom: 10px; }
</style>
</head>
<body>
<div class="header">MARS ROVER CAMERA FEED</div>
<div class="card">
  <img id="cam" src="/capture">
  <div class="status"><div>LINK: ACTIVE</div><div>UPLOAD: SUPABASE</div></div>
</div>
<div class="footer">Autonomous Exploration System</div>
<script>
setInterval(function () { document.getElementById("cam").src = "/capture?" + Date.now(); }, 3000);
</script>
</body>
</html>
)rawliteral";

/* ================= WEB HANDLERS ================= */
esp_err_t index_handler(httpd_req_t *req) {
    httpd_resp_set_type(req, "text/html");
    httpd_resp_send(req, html_page, HTTPD_RESP_USE_STRLEN);
    return ESP_OK;
}

esp_err_t capture_handler(httpd_req_t *req) {
    digitalWrite(LED_PIN, HIGH); delay(40);
    camera_fb_t * fb = esp_camera_fb_get();
    digitalWrite(LED_PIN, LOW);
    if (!fb) { httpd_resp_send_500(req); return ESP_FAIL; }
    httpd_resp_set_type(req, "image/jpeg");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);
    esp_camera_fb_return(fb);
    return res;
}

/* ================= WEB SERVER ================= */
void start_web_server() {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    httpd_start(&server, &config);
    httpd_uri_t index_uri = { "/", HTTP_GET, index_handler };
    httpd_register_uri_handler(server, &index_uri);
    httpd_uri_t capture_uri = { "/capture", HTTP_GET, capture_handler };
    httpd_register_uri_handler(server, &capture_uri);
}

/* ================= TIMER ================= */
void timer_cb(void *arg) { capture_flag = true; }

/* ================= CAPTURE IMAGE ================= */
void capture_for_upload() {
    Serial.println("Capturing image for upload...");
    digitalWrite(LED_PIN, HIGH); delay(100); // More delay for exposure
    camera_fb_t * fb = esp_camera_fb_get();
    digitalWrite(LED_PIN, LOW);
    if (!fb) {
        Serial.println("Camera capture failed!");
        return;
    }

    if (jpg_buffer) free(jpg_buffer);
    jpg_buffer = (uint8_t*)malloc(fb->len);
    if (!jpg_buffer) {
        Serial.println("Malloc failed!");
        esp_camera_fb_return(fb);
        return;
    }
    memcpy(jpg_buffer, fb->buf, fb->len);
    jpg_buffer_len = fb->len;
    esp_camera_fb_return(fb);
    Serial.printf("Captured %u bytes\n", jpg_buffer_len);
}

/* ================= UPLOAD TO SUPABASE STORAGE ================= */
void upload_to_supabase() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi disconnected! Cannot upload.");
        return;
    }
    if (!jpg_buffer || jpg_buffer_len == 0) {
        Serial.println("No image data buffer!");
        return;
    }

    imageCounter++;
    String filename = "capture_" + String(millis()) + "_" + String(imageCounter) + ".jpg";
    // Construct full URL including object name
    String uploadUrl = supabaseUrl + "/storage/v1/object/" + bucketName + "/" + filename;
    
    Serial.println("--------------------------------");
    Serial.print("Uploading to: "); Serial.println(uploadUrl);
    
    // Explicitly use WiFiClientSecure and setInsecure to skip cert validation
    WiFiClientSecure client;
    client.setInsecure();
    
    HTTPClient http;
    // Begin with the secure client
    if (!http.begin(client, uploadUrl)) {
        Serial.println("Unable to connect to Supabase!");
        return;
    }

    http.addHeader("Content-Type", "image/jpeg");
    http.addHeader("apikey", supabaseKey);
    http.addHeader("Authorization", "Bearer " + supabaseKey);
    http.addHeader("x-upsert", "true"); // Overwrite if exists
    
    int httpResponseCode = http.POST(jpg_buffer, jpg_buffer_len);
    
    if (httpResponseCode > 0) {
        Serial.printf("Supabase HTTP Status: %d\n", httpResponseCode);
        String response = http.getString();
        Serial.println("Supabase Response: " + response);
        
        if (httpResponseCode == 200 || httpResponseCode == 201) {
            Serial.println("SUCCESS: Image uploaded!");
            String publicUrl = supabaseUrl + "/storage/v1/object/public/" + bucketName + "/" + filename;
            save_image_url_to_db(publicUrl);
        } else {
            Serial.println("FAILURE: Upload disallowed or error.");
        }
    } else {
        Serial.printf("HTTP POST Failed, Error: %s\n", http.errorToString(httpResponseCode).c_str());
    }
    
    http.end();
}

/* ================= SAVE IMAGE URL TO DATABASE ================= */
void save_image_url_to_db(String imageUrl) {
    WiFiClientSecure client;
    client.setInsecure();
    
    HTTPClient http;
    String dbUrl = supabaseUrl + "/rest/v1/camera_captures";
    
    if (!http.begin(client, dbUrl)) return;
    
    http.addHeader("Content-Type", "application/json");
    http.addHeader("apikey", supabaseKey);
    http.addHeader("Authorization", "Bearer " + supabaseKey);
    http.addHeader("Prefer", "return=minimal");
    
    String payload = "{\"image_url\":\"" + imageUrl + "\"}";
    int code = http.POST(payload);
    
    if (code == 201) Serial.println("DB Update Success");
    else Serial.printf("DB Update Failed: %d\n", code);
    
    http.end();
}

/* ================= SETUP ================= */
void setup() {
    Serial.begin(115200);
    // Give Serial time to start
    delay(2000);
    Serial.println("\n\n=== RESTARTING ESP32-CAM ===");
    
    pinMode(LED_PIN, OUTPUT);

    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;
    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;
    config.pin_sscb_sda = SIOD_GPIO_NUM;
    config.pin_sscb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 12; // Lower quality to reduce size/timeout
    config.fb_count = 1;

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("Camera Init Failed: 0x%x\n", err);
        return;
    }

    sensor_t * s = esp_camera_sensor_get();
    s->set_brightness(s, 1);
    s->set_contrast(s, 1);
    s->set_saturation(s, 0);

    WiFi.mode(WIFI_AP_STA);
    WiFi.softAP(ssid_ap, password_ap);
    WiFi.begin(ssid_sta, password_sta);
    
    Serial.print("Connecting to WiFi: "); Serial.println(ssid_sta);
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500);
        Serial.print(".");
        attempts++;
    }
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi Connected! IP: " + WiFi.localIP().toString());
    } else {
        Serial.println("\nERROR: Connect Failed! Uploads will fail.");
    }

    start_web_server();
    Serial.println("Web server ready");

    esp_timer_create_args_t timer_args = { .callback = &timer_cb, .name = "mars_timer" };
    esp_timer_create(&timer_args, &capture_timer);
    esp_timer_start_periodic(capture_timer, 10000000); // 10 seconds (slower for debugging)
    
    Serial.println("System Ready. Waiting for timer...");
}

/* ================= LOOP ================= */
void loop() {
    if (capture_flag) {
        capture_for_upload();
        upload_to_supabase();
        capture_flag = false;
        Serial.println("--- Cycle Done ---");
    }
    delay(10);
}