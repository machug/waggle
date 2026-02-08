// Waggle Sensor Node — Main entry point.
//
// Lifecycle on each wake:
//   1. Check provisioning pin (GPIO27) — if LOW, enter serial console
//   2. Load NVS config (hive ID, bridge MAC, calibration)
//   3. Verify configuration — if unconfigured, blink and light-sleep
//   4. Initialise sensors
//   5. Read all sensors
//   6. Take bee counter snapshot
//   7. Build 48-byte payload with CRC-8 (msg_type 0x02)
//   8. Transmit via ESP-NOW (up to 3 retries)
//   9. Light sleep for WAKE_INTERVAL_SEC (ISRs remain active)

#include <Arduino.h>
#include <esp_sleep.h>

#include "config.h"
#include "payload.h"
#include "sensors.h"
#include "comms.h"
#include "provision.h"
#include "bee_counter.h"

// ── Bee counter lane configuration ──────────────────────────────────
// Enable all 4 lanes by default.  Override via NVS in future.
#define DEFAULT_LANE_MASK  0x0F

// ── Sequence counter — survives light sleep in RTC memory ───────────
RTC_DATA_ATTR static uint16_t s_sequence = 0;

// ── Track whether bee counter has been initialised ──────────────────
static bool s_bee_counter_ready = false;

// ── First-boot detection ────────────────────────────────────────────
static bool is_first_boot() {
    esp_reset_reason_t reason = esp_reset_reason();
    // POWERON or UNKNOWN (brownout recovery) indicate a fresh start.
    // DEEPSLEEP indicates a normal wake cycle (not first boot).
    return (reason == ESP_RST_POWERON || reason == ESP_RST_UNKNOWN);
}

// ── Light sleep helper (replaces deep sleep — ISRs keep running) ────
static void enter_light_sleep() {
    log_i("Light sleeping for %d s (seq will be %u)", WAKE_INTERVAL_SEC, s_sequence);
    esp_sleep_enable_timer_wakeup((uint64_t)WAKE_INTERVAL_SEC * 1000000ULL);
    esp_light_sleep_start();
    // Execution resumes here after light sleep
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

// ── Arduino setup (runs once on power-on) ───────────────────────────
void setup() {
    Serial.begin(115200);
    delay(10);
    log_i("Waggle sensor boot — rst_reason=%d", esp_reset_reason());

    // 1. Provisioning check (never returns if pin is LOW)
    provision_check();

    // 2. Load configuration from NVS
    provision_load();

    // 3. Verify we have a valid configuration
    if (!provision_is_configured()) {
        log_w("Not configured (hive_id=%u) — blinking and sleeping",
              provision_hive_id());
        blink_unconfigured();
        // Use light sleep even when unconfigured so loop() can retry
        enter_light_sleep();
        return;
    }

    // 4. Initialise bee counter (must happen before first sleep so ISRs run)
    bee_counter_init(DEFAULT_LANE_MASK);
    s_bee_counter_ready = true;
    log_i("Bee counter initialised, lane_mask=0x%02X", DEFAULT_LANE_MASK);

    // 5. Initialise sensors
    uint8_t flags = sensors_init();

    // 6. Read all sensors
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

    // 7. Take bee counter snapshot (first snapshot — period may be short)
    BeeCountSnapshot bee_snap = bee_counter_snapshot();

    if (bee_snap.bees_in == 65535 || bee_snap.bees_out == 65535) {
        flags |= FLAG_MEASUREMENT_CLAMPED;
    }
    if (bee_snap.stuck_mask != 0) {
        flags |= FLAG_COUNTER_STUCK;
    }

    // 8. Build 48-byte payload
    bee_count_payload_t payload;
    payload_build_v2(&payload,
                     provision_hive_id(),
                     s_sequence,
                     weight,
                     temp,
                     humidity,
                     pressure,
                     battery,
                     flags,
                     bee_snap.bees_in,
                     bee_snap.bees_out,
                     bee_snap.period_ms,
                     bee_snap.lane_mask,
                     bee_snap.stuck_mask);

    log_i("Payload: hive=%u seq=%u wt=%d t=%d h=%u p=%u bat=%u flags=0x%02X "
          "in=%u out=%u period=%u lanes=0x%02X stuck=0x%02X crc=0x%02X",
          payload.hive_id, payload.sequence, payload.weight_g,
          payload.temp_c_x100, payload.humidity_x100, payload.pressure_hpa_x10,
          payload.battery_mv, payload.flags,
          payload.bees_in, payload.bees_out, payload.period_ms,
          payload.lane_mask, payload.stuck_mask, payload.crc);

    // 9. Transmit via ESP-NOW
    if (comms_init(provision_bridge_mac())) {
        bool ok = comms_send((const uint8_t*)&payload, PAYLOAD_SIZE_V2);
        if (!ok) {
            log_e("Payload delivery failed after retries");
        }
    } else {
        log_e("ESP-NOW init failed — skipping transmission");
    }

    // 10. Increment sequence and light sleep
    s_sequence++;
    enter_light_sleep();
}

// ── loop() — runs after each light sleep wake ───────────────────────
// With light sleep, execution continues in loop() after each wake.
// We re-read sensors and transmit on each wake cycle.
void loop() {
    log_i("Waggle sensor wake — seq=%u", s_sequence);

    // Re-check provisioning each wake
    provision_check();
    provision_load();

    if (!provision_is_configured()) {
        log_w("Not configured — sleeping");
        blink_unconfigured();
        enter_light_sleep();
        return;
    }

    // Ensure bee counter is initialised (in case setup() skipped it)
    if (!s_bee_counter_ready) {
        bee_counter_init(DEFAULT_LANE_MASK);
        s_bee_counter_ready = true;
    }

    // Read sensors
    uint8_t flags = sensors_init();
    int32_t  weight      = read_weight_g(&flags);
    int16_t  temp        = read_temperature_x100(&flags);
    uint16_t humidity    = read_humidity_x100(&flags);
    uint16_t pressure    = read_pressure_x10(&flags);
    uint16_t battery     = read_battery_mv();

    if (is_first_boot()) {
        flags |= FLAG_FIRST_BOOT;
    }
    if (battery < LOW_BATTERY_MV) {
        flags |= FLAG_LOW_BATTERY;
    }

    // Take bee counter snapshot (accumulated since last wake)
    BeeCountSnapshot bee_snap = bee_counter_snapshot();

    if (bee_snap.bees_in == 65535 || bee_snap.bees_out == 65535) {
        flags |= FLAG_MEASUREMENT_CLAMPED;
    }
    if (bee_snap.stuck_mask != 0) {
        flags |= FLAG_COUNTER_STUCK;
    }

    // Build 48-byte payload
    bee_count_payload_t payload;
    payload_build_v2(&payload,
                     provision_hive_id(),
                     s_sequence,
                     weight,
                     temp,
                     humidity,
                     pressure,
                     battery,
                     flags,
                     bee_snap.bees_in,
                     bee_snap.bees_out,
                     bee_snap.period_ms,
                     bee_snap.lane_mask,
                     bee_snap.stuck_mask);

    log_i("Payload: hive=%u seq=%u wt=%d t=%d h=%u p=%u bat=%u flags=0x%02X "
          "in=%u out=%u period=%u lanes=0x%02X stuck=0x%02X crc=0x%02X",
          payload.hive_id, payload.sequence, payload.weight_g,
          payload.temp_c_x100, payload.humidity_x100, payload.pressure_hpa_x10,
          payload.battery_mv, payload.flags,
          payload.bees_in, payload.bees_out, payload.period_ms,
          payload.lane_mask, payload.stuck_mask, payload.crc);

    // Transmit via ESP-NOW
    if (comms_init(provision_bridge_mac())) {
        bool ok = comms_send((const uint8_t*)&payload, PAYLOAD_SIZE_V2);
        if (!ok) {
            log_e("Payload delivery failed after retries");
        }
    } else {
        log_e("ESP-NOW init failed — skipping transmission");
    }

    // Increment sequence and sleep
    s_sequence++;
    enter_light_sleep();
}
