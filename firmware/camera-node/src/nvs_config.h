// Waggle Camera Node — NVS configuration storage.
// Stores device identity, WiFi credentials, and hub URL in non-volatile storage.
// These values are provisioned once (e.g. via serial or a provisioning tool)
// and persist across deep sleep cycles and firmware updates.

#pragma once

// ── Device configuration struct ─────────────────────────────────────
// All fields are null-terminated C strings except sleep_sec.
struct DeviceConfig {
    char device_id[37];   // UUID v4 (36 chars + null)
    char api_key[65];     // API key (up to 64 chars + null)
    char hive_id[8];      // Hive ID string (up to 7 chars + null)
    char wifi_ssid[33];   // WiFi SSID (up to 32 chars + null)
    char wifi_pass[65];   // WiFi password (up to 64 chars + null)
    char hub_url[128];    // Hub base URL, e.g. "http://192.168.1.50:8000"
    int  sleep_sec;       // Deep sleep interval in seconds (0 = use DEFAULT_SLEEP_SEC)
};

// Load configuration from NVS "waggle" namespace.
// Populates all fields of cfg.  Missing string fields are set to empty (""),
// missing sleep_sec is set to 0 (caller should fall back to DEFAULT_SLEEP_SEC).
// Returns true if at least device_id and wifi_ssid are non-empty (minimal viable config).
bool nvs_load_config(DeviceConfig& cfg);

// Save configuration to NVS "waggle" namespace.
// Writes all fields.  Returns true on success.
bool nvs_save_config(const DeviceConfig& cfg);
