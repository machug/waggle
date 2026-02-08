/**
 * Waggle Bridge — ESP-NOW to USB-serial gateway.
 *
 * Data flow:
 *   1. Sensor node sends 32-byte payload via ESP-NOW.
 *   2. ESP-NOW callback fires with sender MAC (6 bytes) + payload (32 bytes).
 *   3. We build a 38-byte frame: [MAC][payload].
 *   4. COBS-encode the frame (max 39 output bytes for 38-byte input).
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

/**
 * ESP-NOW receive callback.
 *
 * Called from the WiFi task when an ESP-NOW packet arrives.
 * We validate the length, build the frame, COBS-encode, and write to Serial.
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

    // Validate expected payload size
    if (data_len != PAYLOAD_LEN) {
        log_w("Unexpected payload size: %d (expected %d)", data_len, PAYLOAD_LEN);
        return;
    }

    // Build 38-byte frame: [6-byte MAC][32-byte payload]
    uint8_t frame[FRAME_LEN];
    memcpy(frame, mac, MAC_LEN);
    memcpy(frame + MAC_LEN, data, PAYLOAD_LEN);

    // COBS-encode the frame
    uint8_t encoded[COBS_MAX_OUTPUT];
    size_t encoded_len = cobs_encode(frame, FRAME_LEN, encoded);

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
