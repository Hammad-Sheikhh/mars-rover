// Copy this file to secrets.h (same folder) and fill in your values.
// secrets.h is git-ignored. Never commit real credentials.
#pragma once

// Station mode: the WiFi network with internet access (for Supabase uploads)
#define WIFI_SSID         "your-wifi-name"
#define WIFI_PASS         "your-wifi-password"

// Access point hosted by this board (WPA2 needs at least 8 characters)
#define AP_SSID           "ESP32-Car-AP"
#define AP_PASS           "change-me-123"

// Supabase project settings -> API. Use the anon (public) key, never service_role.
#define SUPABASE_URL      "https://your-project-ref.supabase.co"
#define SUPABASE_ANON_KEY "your-anon-key"

// Shared secret for Jev Auto: the Earth Station sends it with every move (POST /jev/cmd).
// Must equal ROVER_CMD_TOKEN in the laptop's .env. Use 8+ random characters, e.g.:
//   python -c "import secrets; print(secrets.token_urlsafe(16))"
#define ROVER_CMD_TOKEN   "change-me-to-a-random-token"
