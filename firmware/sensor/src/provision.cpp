// Waggle Sensor Node — Provisioning implementation.
// Serial commands at 115200 baud:
//   SET_ID <1-250>           Set hive ID
//   SET_BRIDGE <MAC>         Set bridge MAC (AA:BB:CC:DD:EE:FF)
//   TARE                     Zero the load cell (store offset in NVS)
//   CALIBRATE <grams>        Place known weight, compute scale factor
//   STATUS                   Print current config
//   REBOOT                   Restart the ESP32

#include "provision.h"
#include "config.h"
#include "payload.h"

#include <Arduino.h>
#include <Preferences.h>
#include <HX711.h>

// ── Shared calibration state (also used by sensors.cpp) ─────────────
float hx711_scale_factor = 1.0f;
long  hx711_offset       = 0;

// ── Module state ────────────────────────────────────────────────────
static uint8_t  s_hive_id = 0;
static uint8_t  s_bridge_mac[6] = {0};
static bool     s_bridge_mac_set = false;

// ── Helpers ─────────────────────────────────────────────────────────
// Parse "AA:BB:CC:DD:EE:FF" into a 6-byte array.  Returns true on success.
static bool parse_mac(const char* str, uint8_t* mac) {
    unsigned int m[6];
    if (sscanf(str, "%x:%x:%x:%x:%x:%x",
               &m[0], &m[1], &m[2], &m[3], &m[4], &m[5]) != 6) {
        return false;
    }
    for (int i = 0; i < 6; i++) {
        if (m[i] > 0xFF) return false;
        mac[i] = (uint8_t)m[i];
    }
    return true;
}

static void print_mac(const uint8_t* mac) {
    Serial.printf("%02X:%02X:%02X:%02X:%02X:%02X",
                  mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

static void blink_led(int count, int on_ms, int off_ms) {
    for (int i = 0; i < count; i++) {
        digitalWrite(LED_PIN, HIGH);
        delay(on_ms);
        digitalWrite(LED_PIN, LOW);
        delay(off_ms);
    }
}

// ── NVS Load ────────────────────────────────────────────────────────
void provision_load() {
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, true);  // read-only

    s_hive_id = prefs.getUChar("hive_id", 0);

    size_t mac_len = prefs.getBytes("bridge_mac", s_bridge_mac, 6);
    s_bridge_mac_set = (mac_len == 6);

    hx711_scale_factor = prefs.getFloat("hx_scale", 1.0f);
    hx711_offset       = prefs.getLong("hx_offset", 0);

    prefs.end();

    log_i("NVS loaded: hive_id=%u, bridge_mac_set=%d, scale=%.2f, offset=%ld",
          s_hive_id, s_bridge_mac_set, hx711_scale_factor, hx711_offset);
}

// ── NVS Save helpers ────────────────────────────────────────────────
static void nvs_save_hive_id(uint8_t id) {
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, false);
    prefs.putUChar("hive_id", id);
    prefs.end();
}

static void nvs_save_bridge_mac(const uint8_t* mac) {
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, false);
    prefs.putBytes("bridge_mac", mac, 6);
    prefs.end();
}

static void nvs_save_calibration(float scale, long offset) {
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, false);
    prefs.putFloat("hx_scale", scale);
    prefs.putLong("hx_offset", offset);
    prefs.end();
}

// ── Provisioning serial loop ────────────────────────────────────────
static void provision_loop() {
    Serial.println();
    Serial.println("=== WAGGLE PROVISIONING MODE ===");
    Serial.println("Commands: SET_ID <n>, SET_BRIDGE <MAC>, TARE,");
    Serial.println("          CALIBRATE <grams>, STATUS, REBOOT");
    Serial.println();

    // Temporary HX711 for tare/calibrate
    HX711 scale_prov;
    scale_prov.begin(HX711_DOUT_PIN, HX711_SCK_PIN);

    while (true) {
        Serial.print("waggle> ");

        // Wait for serial input
        while (!Serial.available()) {
            blink_led(1, 100, 400);  // slow blink while waiting
        }

        String line = Serial.readStringUntil('\n');
        line.trim();
        if (line.length() == 0) continue;

        // ── SET_ID ──────────────────────────────────────────────
        if (line.startsWith("SET_ID ")) {
            int id = line.substring(7).toInt();
            if (id < 1 || id > 250) {
                Serial.println("ERROR: ID must be 1-250");
                continue;
            }
            s_hive_id = (uint8_t)id;
            nvs_save_hive_id(s_hive_id);
            Serial.printf("OK: hive_id=%u\n", s_hive_id);
        }
        // ── SET_BRIDGE ──────────────────────────────────────────
        else if (line.startsWith("SET_BRIDGE ")) {
            String mac_str = line.substring(11);
            mac_str.trim();
            uint8_t mac[6];
            if (!parse_mac(mac_str.c_str(), mac)) {
                Serial.println("ERROR: Invalid MAC format (use AA:BB:CC:DD:EE:FF)");
                continue;
            }
            memcpy(s_bridge_mac, mac, 6);
            s_bridge_mac_set = true;
            nvs_save_bridge_mac(s_bridge_mac);
            Serial.print("OK: bridge_mac=");
            print_mac(s_bridge_mac);
            Serial.println();
        }
        // ── TARE ────────────────────────────────────────────────
        else if (line == "TARE") {
            if (!scale_prov.wait_ready_timeout(1000)) {
                Serial.println("ERROR: HX711 not ready");
                continue;
            }
            Serial.println("Taring... remove all weight from the scale.");
            delay(2000);
            scale_prov.tare(20);  // average 20 readings
            hx711_offset = scale_prov.get_offset();
            nvs_save_calibration(hx711_scale_factor, hx711_offset);
            Serial.printf("OK: offset=%ld\n", hx711_offset);
        }
        // ── CALIBRATE ───────────────────────────────────────────
        else if (line.startsWith("CALIBRATE ")) {
            float known_grams = line.substring(10).toFloat();
            if (known_grams <= 0) {
                Serial.println("ERROR: Specify positive weight in grams");
                continue;
            }
            if (!scale_prov.wait_ready_timeout(1000)) {
                Serial.println("ERROR: HX711 not ready");
                continue;
            }
            Serial.printf("Calibrating with %.1f g... place weight now.\n", known_grams);
            delay(3000);
            // Read raw average and compute scale factor
            long raw = scale_prov.read_average(20);
            if (raw == hx711_offset) {
                Serial.println("ERROR: Raw reading equals offset — no weight detected?");
                continue;
            }
            hx711_scale_factor = (float)(raw - hx711_offset) / known_grams;
            nvs_save_calibration(hx711_scale_factor, hx711_offset);
            Serial.printf("OK: scale_factor=%.4f\n", hx711_scale_factor);
        }
        // ── STATUS ──────────────────────────────────────────────
        else if (line == "STATUS") {
            Serial.println("--- Waggle Sensor Status ---");
            Serial.printf("  hive_id:     %u\n", s_hive_id);
            Serial.print("  bridge_mac:  ");
            if (s_bridge_mac_set) {
                print_mac(s_bridge_mac);
            } else {
                Serial.print("(not set)");
            }
            Serial.println();
            Serial.printf("  hx711_scale: %.4f\n", hx711_scale_factor);
            Serial.printf("  hx711_offset:%ld\n", hx711_offset);
            Serial.printf("  configured:  %s\n", provision_is_configured() ? "YES" : "NO");
            Serial.println("----------------------------");
        }
        // ── REBOOT ──────────────────────────────────────────────
        else if (line == "REBOOT") {
            Serial.println("Rebooting...");
            delay(500);
            ESP.restart();
        }
        // ── Unknown ─────────────────────────────────────────────
        else {
            Serial.println("ERROR: Unknown command. Try STATUS for help.");
        }
    }
}

// ── Check provisioning pin ──────────────────────────────────────────
void provision_check() {
    pinMode(PROVISION_PIN, INPUT_PULLUP);
    delay(50);  // debounce

    if (digitalRead(PROVISION_PIN) == LOW) {
        log_i("Provisioning pin LOW — entering provisioning mode");
        provision_loop();
        // provision_loop never returns (user must REBOOT)
    }
}

// ── Accessors ───────────────────────────────────────────────────────
uint8_t provision_hive_id() {
    return s_hive_id;
}

const uint8_t* provision_bridge_mac() {
    return s_bridge_mac;
}

bool provision_is_configured() {
    return (s_hive_id != 0) && s_bridge_mac_set;
}
