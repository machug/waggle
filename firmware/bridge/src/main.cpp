/**
 * Waggle Bridge — ESP-NOW to USB-serial gateway.
 *
 * Data flow:
 *   1. Sensor node sends payload via ESP-NOW (32 bytes Phase 1, 48 bytes Phase 2).
 *   2. ESP-NOW callback fires with sender MAC (6 bytes) + payload.
 *   3. We build a frame: [MAC][payload] (38 or 54 bytes).
 *   4. COBS-encode the frame and append 0x00 delimiter.
 *   5. Write [COBS bytes][0x00 delimiter] to Serial (USB).
 *   6. Pi hub reads from /dev/ttyUSBx, decodes COBS, and processes.
 */

#ifndef UNIT_TEST  // Exclude hardware code from native test builds

#include <Arduino.h>

#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

#include "cobs.h"
#include "config.h"

// LED state toggle for visual feedback
static volatile bool led_state = false;

// Error counter for unexpected payload sizes (for diagnostics)
static volatile uint32_t err_bad_len = 0;

/**
 * ESP-NOW receive callback.
 *
 * Called from the WiFi task when an ESP-NOW packet arrives.
 * We validate the length, build the frame, COBS-encode, and write to Serial.
 *
 * Accepts Phase 1 payloads (32 bytes) and Phase 2 payloads (48 bytes).
 * The bridge does NOT parse payload content — it just forwards to the Pi hub.
 *
 * Note: Serial.write() is safe to call from the ESP-NOW callback context
 * on ESP32 Arduino core because it only copies to the TX buffer.
 */
#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(5, 1, 0)
static void on_data_recv(const esp_now_recv_info_t* info, const uint8_t* data, int data_len) {
    const uint8_t* mac = info->src_addr;
#else
static void on_data_recv(const uint8_t* mac, const uint8_t* data, int data_len) {
#endif

    // Validate expected payload size: Phase 1 (32 bytes) or Phase 2 (48 bytes)
    if (data_len != (int)PAYLOAD_LEN_P1 && data_len != (int)PAYLOAD_LEN_P2) {
        log_w("Unexpected payload size: %d (expected %d or %d)",
              data_len, PAYLOAD_LEN_P1, PAYLOAD_LEN_P2);
        err_bad_len++;
        return;
    }

    // Build frame: [6-byte MAC][payload]
    const size_t frame_len = MAC_LEN + (size_t)data_len;
    uint8_t frame[MAX_DECODED_SIZE];
    memcpy(frame, mac, MAC_LEN);
    memcpy(frame + MAC_LEN, data, (size_t)data_len);

    // COBS-encode the frame
    uint8_t encoded[COBS_MAX_OUTPUT];
    size_t encoded_len = cobs_encode(frame, frame_len, encoded);

    // Write to serial: [COBS data][0x00 delimiter]
    Serial.write(encoded, encoded_len);
    Serial.write(FRAME_DELIMITER);

    // Toggle LED for visual feedback
    led_state = !led_state;
    digitalWrite(LED_PIN, led_state ? HIGH : LOW);
}

void setup() {
    // Serial — USB connection to Pi hub
    Serial.begin(SERIAL_BAUD);
    while (!Serial) {
        delay(10);
    }

    // LED
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);

    // WiFi — station mode required for ESP-NOW
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();  // No need to connect to an AP

    // Log the bridge MAC address so operator can configure sensor nodes
    log_i("Waggle Bridge MAC: %s", WiFi.macAddress().c_str());

    // ESP-NOW
    if (esp_now_init() != ESP_OK) {
        log_e("ESP-NOW init failed");
        // Blink LED rapidly to indicate fatal error
        while (true) {
            digitalWrite(LED_PIN, HIGH);
            delay(100);
            digitalWrite(LED_PIN, LOW);
            delay(100);
        }
    }

    esp_now_register_recv_cb(on_data_recv);

    log_i("Waggle Bridge ready — listening for ESP-NOW packets");
}

void loop() {
    // All work is done in the ESP-NOW callback.
    // Main loop just yields to avoid watchdog triggers.
    delay(100);
}

#endif // UNIT_TEST
