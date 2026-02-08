// Waggle Sensor Node — Main entry point.
//
// Lifecycle on each wake:
//   1. Check provisioning pin (GPIO27) — if LOW, enter serial console
//   2. Load NVS config (hive ID, bridge MAC, calibration)
//   3. Verify configuration — if unconfigured, blink and deep-sleep
//   4. Initialise sensors
//   5. Read all sensors
//   6. Build 32-byte payload with CRC-8
//   7. Transmit via ESP-NOW (up to 3 retries)
//   8. Deep sleep for WAKE_INTERVAL_SEC

#include <Arduino.h>
#include <esp_sleep.h>

#include "config.h"
#include "payload.h"
#include "sensors.h"
#include "comms.h"
#include "provision.h"

// ── Sequence counter — survives deep sleep in RTC memory ────────────
RTC_DATA_ATTR static uint16_t s_sequence = 0;

// ── First-boot detection ────────────────────────────────────────────
static bool is_first_boot() {
    esp_reset_reason_t reason = esp_reset_reason();
    // POWERON or UNKNOWN (brownout recovery) indicate a fresh start.
    // DEEPSLEEP indicates a normal wake cycle (not first boot).
    return (reason == ESP_RST_POWERON || reason == ESP_RST_UNKNOWN);
}

// ── Deep sleep helper ───────────────────────────────────────────────
static void enter_deep_sleep() {
    log_i("Sleeping for %d s (seq will be %u)", WAKE_INTERVAL_SEC, s_sequence);
    esp_sleep_enable_timer_wakeup((uint64_t)WAKE_INTERVAL_SEC * 1000000ULL);
    esp_deep_sleep_start();
    // Execution never reaches here
}

// ── Blink pattern for unconfigured state ────────────────────────────
static void blink_unconfigured() {
    pinMode(LED_PIN, OUTPUT);
    for (int i = 0; i < 5; i++) {
        digitalWrite(LED_PIN, HIGH);
        delay(100);
        digitalWrite(LED_PIN, LOW);
        delay(100);
    }
}

// ── Arduino setup (runs every wake) ─────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(10);
    log_i("Waggle sensor wake — seq=%u, rst_reason=%d", s_sequence, esp_reset_reason());

    // 1. Provisioning check (never returns if pin is LOW)
    provision_check();

    // 2. Load configuration from NVS
    provision_load();

    // 3. Verify we have a valid configuration
    if (!provision_is_configured()) {
        log_w("Not configured (hive_id=%u) — blinking and sleeping",
              provision_hive_id());
        blink_unconfigured();
        enter_deep_sleep();
        return;  // unreachable
    }

    // 4. Initialise sensors
    uint8_t flags = sensors_init();

    // 5. Read all sensors
    int32_t  weight      = read_weight_g(&flags);
    int16_t  temp        = read_temperature_x100(&flags);
    uint16_t humidity    = read_humidity_x100(&flags);
    uint16_t pressure    = read_pressure_x10(&flags);
    uint16_t battery     = read_battery_mv();

    // Set additional flags
    if (is_first_boot()) {
        flags |= FLAG_FIRST_BOOT;
    }
    if (battery < LOW_BATTERY_MV) {
        flags |= FLAG_LOW_BATTERY;
    }

    // 6. Build payload
    sensor_payload_t payload;
    payload_build(&payload,
                  provision_hive_id(),
                  s_sequence,
                  weight,
                  temp,
                  humidity,
                  pressure,
                  battery,
                  flags);

    log_i("Payload: hive=%u seq=%u wt=%d t=%d h=%u p=%u bat=%u flags=0x%02X crc=0x%02X",
          payload.hive_id, payload.sequence, payload.weight_g,
          payload.temp_c_x100, payload.humidity_x100, payload.pressure_hpa_x10,
          payload.battery_mv, payload.flags, payload.crc);

    // 7. Transmit via ESP-NOW
    if (comms_init(provision_bridge_mac())) {
        bool ok = comms_send((const uint8_t*)&payload, PAYLOAD_SIZE);
        if (!ok) {
            log_e("Payload delivery failed after retries");
        }
    } else {
        log_e("ESP-NOW init failed — skipping transmission");
    }

    // 8. Increment sequence and deep sleep
    s_sequence++;
    enter_deep_sleep();
}

// loop() is never reached because setup() always ends in deep sleep.
void loop() {
    // Should never execute.  Safety net: sleep if we somehow get here.
    enter_deep_sleep();
}
