// Waggle Camera Node — Main entry point.
//
// Lifecycle on each wake from deep sleep:
//   1. Read NVS config (device_id, api_key, hive_id, wifi_ssid, wifi_pass, hub_url)
//   2. Init camera (FRAMESIZE_VGA, JPEG quality 12)
//   3. Capture JPEG frame
//   4. Connect to WiFi (timeout 15 s)
//   5. NTP sync (if first boot or >24 h since last sync)
//   6. HTTP POST multipart to {hub_url}/api/hives/{hive_id}/photos
//   7. Disconnect WiFi
//   8. Deinit camera
//   9. Deep sleep for configured interval (default 15 minutes)
//
// Unlike the sensor node (which uses light sleep to keep ISRs running),
// the camera node uses deep sleep since there are no background tasks
// between captures.  This saves significant power.

#include <Arduino.h>
#include <esp_sleep.h>

#include "config.h"
#include "nvs_config.h"
#include "camera.h"
#include "wifi_upload.h"
#include "ntp_sync.h"

// ── RTC data — survives deep sleep ──────────────────────────────────
RTC_DATA_ATTR static uint32_t s_boot_count = 0;

// ── First-boot detection ────────────────────────────────────────────
static bool is_first_boot() {
    esp_reset_reason_t reason = esp_reset_reason();
    return (reason == ESP_RST_POWERON || reason == ESP_RST_UNKNOWN);
}

// ── Build the upload URL from hub_url and hive_id ───────────────────
static String build_upload_url(const char* hub_url, const char* hive_id) {
    String url = String(hub_url);
    // Strip trailing slash if present
    if (url.endsWith("/")) {
        url.remove(url.length() - 1);
    }
    url += "/api/hives/";
    url += hive_id;
    url += "/photos";
    return url;
}

// ── Enter deep sleep ────────────────────────────────────────────────
static void enter_deep_sleep(int sleep_sec) {
    int duration = (sleep_sec > 0) ? sleep_sec : DEFAULT_SLEEP_SEC;
    log_i("Entering deep sleep for %d s (boot #%u)", duration, s_boot_count);
    esp_sleep_enable_timer_wakeup((uint64_t)duration * 1000000ULL);
    esp_deep_sleep_start();
    // Execution stops here — next wake restarts from setup()
}

// ── Arduino setup (runs on every wake from deep sleep) ──────────────
void setup() {
    Serial.begin(115200);
    delay(10);

    s_boot_count++;
    log_i("Waggle camera boot #%u — rst_reason=%d", s_boot_count, esp_reset_reason());

    // ── 1. Load NVS configuration ───────────────────────────────────
    DeviceConfig cfg;
    if (!nvs_load_config(cfg)) {
        log_e("Configuration incomplete — cannot operate. Sleeping.");
        enter_deep_sleep(DEFAULT_SLEEP_SEC);
        return;
    }

    // ── 2. Init camera ──────────────────────────────────────────────
    if (!camera_init()) {
        log_e("Camera init failed — sleeping");
        enter_deep_sleep(cfg.sleep_sec);
        return;
    }

    // ── 3. Capture JPEG frame ───────────────────────────────────────
    camera_fb_t* fb = camera_capture();
    if (fb == nullptr) {
        log_e("Capture failed — deinit and sleep");
        camera_deinit();
        enter_deep_sleep(cfg.sleep_sec);
        return;
    }

    log_i("Photo captured: %u bytes", fb->len);

    // ── 4. Connect to WiFi ──────────────────────────────────────────
    if (!wifi_connect(cfg.wifi_ssid, cfg.wifi_pass, WIFI_TIMEOUT_MS)) {
        log_e("WiFi failed — releasing frame and sleeping");
        camera_release(fb);
        camera_deinit();
        enter_deep_sleep(cfg.sleep_sec);
        return;
    }

    // ── 5. NTP sync (first boot or >24 h since last) ───────────────
    if (is_first_boot() || should_sync()) {
        if (!ntp_init()) {
            log_w("NTP sync failed — timestamps may be inaccurate");
            // Continue anyway — stale time is better than no upload
        }
    }

    String timestamp = get_timestamp_iso8601();
    log_i("Timestamp: %s", timestamp.c_str());

    // ── 6. Upload photo ─────────────────────────────────────────────
    String url = build_upload_url(cfg.hub_url, cfg.hive_id);
    int http_code = upload_photo(
        url.c_str(),
        cfg.api_key,
        cfg.device_id,
        fb->buf,
        fb->len,
        timestamp.c_str()
    );

    if (http_code >= 200 && http_code < 300) {
        log_i("Upload successful: HTTP %d", http_code);
    } else {
        log_e("Upload failed: HTTP %d", http_code);
    }

    // ── 7. Disconnect WiFi ──────────────────────────────────────────
    wifi_disconnect();

    // ── 8. Release frame and deinit camera ──────────────────────────
    camera_release(fb);
    camera_deinit();

    // ── 9. Deep sleep ───────────────────────────────────────────────
    enter_deep_sleep(cfg.sleep_sec);
}

// ── loop() — never reached (deep sleep restarts from setup()) ───────
void loop() {
    // With deep sleep, the ESP32 resets on each wake and enters setup().
    // This function is required by the Arduino framework but never executes.
}
