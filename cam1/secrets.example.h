// Easiest: put the hotspot details in the repo-root .env and run
//   python -m earth_station.secrets
// It writes secrets.h for both boards. Or copy this file to secrets.h (same folder) by hand.
// secrets.h is git-ignored. Never commit real credentials.
#pragma once

// The phone hotspot that the rover, camera and laptop all join (2.4 GHz)
#define WIFI_SSID         "your-wifi-name"
#define WIFI_PASS         "your-wifi-password"

// Access point hosted by this board (WPA2 needs at least 8 characters)
#define AP_SSID           "ESP32_CAM_MARS"
#define AP_PASS           "change-me-123"

// Supabase project settings -> API. Use the anon (public) key, never service_role.
#define SUPABASE_URL      "https://your-project-ref.supabase.co"
#define SUPABASE_ANON_KEY "your-anon-key"
