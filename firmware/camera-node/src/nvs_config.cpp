// Waggle Camera Node — NVS configuration implementation.
// Uses the Arduino Preferences library (wraps ESP-IDF NVS).

#include "nvs_config.h"
#include "config.h"

#include <Arduino.h>
#include <Preferences.h>
#include <string.h>

// ── Helper: read a string key from Preferences into a fixed buffer ──
static void prefs_get_str(Preferences& prefs, const char* key, char* buf, size_t buf_len) {
    String val = prefs.getString(key, "");
    strncpy(buf, val.c_str(), buf_len - 1);
    buf[buf_len - 1] = '\0';
}

// ── Public API ──────────────────────────────────────────────────────

bool nvs_load_config(DeviceConfig& cfg) {
    memset(&cfg, 0, sizeof(cfg));

    Preferences prefs;
    if (!prefs.begin(NVS_NAMESPACE, true)) {  // read-only
        log_e("Failed to open NVS namespace '%s'", NVS_NAMESPACE);
        return false;
    }

    prefs_get_str(prefs, "device_id",  cfg.device_id,  sizeof(cfg.device_id));
    prefs_get_str(prefs, "api_key",    cfg.api_key,    sizeof(cfg.api_key));
    prefs_get_str(prefs, "hive_id",    cfg.hive_id,    sizeof(cfg.hive_id));
    prefs_get_str(prefs, "wifi_ssid",  cfg.wifi_ssid,  sizeof(cfg.wifi_ssid));
    prefs_get_str(prefs, "wifi_pass",  cfg.wifi_pass,  sizeof(cfg.wifi_pass));
    prefs_get_str(prefs, "hub_url",    cfg.hub_url,    sizeof(cfg.hub_url));
    cfg.sleep_sec = prefs.getInt("sleep_sec", 0);

    prefs.end();

    log_i("NVS config loaded: device_id=%s hive_id=%s hub_url=%s sleep=%d",
          cfg.device_id, cfg.hive_id, cfg.hub_url, cfg.sleep_sec);

    // Minimal viable config: must have device_id and wifi_ssid
    bool valid = (strlen(cfg.device_id) > 0) && (strlen(cfg.wifi_ssid) > 0);
    if (!valid) {
        log_w("Config incomplete: device_id or wifi_ssid missing");
    }
    return valid;
}

bool nvs_save_config(const DeviceConfig& cfg) {
    Preferences prefs;
    if (!prefs.begin(NVS_NAMESPACE, false)) {  // read-write
        log_e("Failed to open NVS namespace '%s' for writing", NVS_NAMESPACE);
        return false;
    }

    prefs.putString("device_id",  cfg.device_id);
    prefs.putString("api_key",    cfg.api_key);
    prefs.putString("hive_id",    cfg.hive_id);
    prefs.putString("wifi_ssid",  cfg.wifi_ssid);
    prefs.putString("wifi_pass",  cfg.wifi_pass);
    prefs.putString("hub_url",    cfg.hub_url);
    prefs.putInt("sleep_sec",     cfg.sleep_sec);

    prefs.end();

    log_i("NVS config saved: device_id=%s hive_id=%s", cfg.device_id, cfg.hive_id);
    return true;
}
