// Waggle Camera Node — Compile-time defaults and tunables.
// Runtime overrides are loaded from NVS (see nvs_config.h).

#pragma once

#define DEFAULT_SLEEP_SEC   900       // 15 minutes between captures
#define WIFI_TIMEOUT_MS     15000     // 15 seconds to connect
#define NTP_SERVER          "pool.ntp.org"
#define NTP_SYNC_INTERVAL   86400     // Re-sync NTP every 24 hours
#define CAMERA_QUALITY      12        // JPEG quality (0-63, lower = better)
#define CAMERA_FRAMESIZE    FRAMESIZE_VGA

// ── NVS namespace ───────────────────────────────────────────────────
#define NVS_NAMESPACE       "waggle"

// ── LED ─────────────────────────────────────────────────────────────
// AI-Thinker ESP32-CAM has a white flash LED on GPIO4
#define FLASH_LED_PIN       4
