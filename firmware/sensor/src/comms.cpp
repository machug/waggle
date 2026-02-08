// Waggle Sensor Node — ESP-NOW communication implementation.

#include "comms.h"
#include "config.h"

#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <string.h>

// ── Delivery callback state ─────────────────────────────────────────
static volatile bool send_done     = false;
static volatile bool send_success  = false;

static uint8_t peer_mac[6];

// ── Callback: delivery result ───────────────────────────────────────
static void on_data_sent(const uint8_t* mac, esp_now_send_status_t status) {
    send_done    = true;
    send_success = (status == ESP_NOW_SEND_SUCCESS);
}

// ── Init ────────────────────────────────────────────────────────────
bool comms_init(const uint8_t* bridge_mac) {
    memcpy(peer_mac, bridge_mac, 6);

    // Wi-Fi must be initialised for ESP-NOW even though we don't join an AP.
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();   // no AP association needed

    // Lock to the configured channel
    esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);

    if (esp_now_init() != ESP_OK) {
        log_e("ESP-NOW init failed");
        return false;
    }

    esp_now_register_send_cb(on_data_sent);

    // Register bridge as a peer
    esp_now_peer_info_t peer = {};
    memcpy(peer.peer_addr, bridge_mac, 6);
    peer.channel = ESPNOW_CHANNEL;
    peer.encrypt = false;

    if (esp_now_add_peer(&peer) != ESP_OK) {
        log_e("Failed to add bridge peer");
        return false;
    }

    log_i("ESP-NOW ready — bridge %02X:%02X:%02X:%02X:%02X:%02X ch=%d",
          bridge_mac[0], bridge_mac[1], bridge_mac[2],
          bridge_mac[3], bridge_mac[4], bridge_mac[5],
          ESPNOW_CHANNEL);
    return true;
}

// ── Send with retries ───────────────────────────────────────────────
bool comms_send(const uint8_t* data, size_t len) {
    for (int attempt = 1; attempt <= ESPNOW_MAX_RETRIES; attempt++) {
        send_done    = false;
        send_success = false;

        esp_err_t err = esp_now_send(peer_mac, data, len);
        if (err != ESP_OK) {
            log_w("esp_now_send error 0x%X (attempt %d/%d)",
                  err, attempt, ESPNOW_MAX_RETRIES);
            delay(ESPNOW_RETRY_MS);
            continue;
        }

        // Wait for the delivery callback (timeout ~500 ms)
        unsigned long t0 = millis();
        while (!send_done && (millis() - t0 < 500)) {
            delay(1);
        }

        if (send_success) {
            log_i("Payload delivered (attempt %d/%d)", attempt, ESPNOW_MAX_RETRIES);
            return true;
        }

        log_w("Delivery failed (attempt %d/%d)", attempt, ESPNOW_MAX_RETRIES);
        if (attempt < ESPNOW_MAX_RETRIES) {
            delay(ESPNOW_RETRY_MS);
        }
    }

    log_e("All %d send attempts failed", ESPNOW_MAX_RETRIES);
    return false;
}
