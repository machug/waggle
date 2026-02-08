/**
 * Waggle Bridge — Configuration constants.
 *
 * The bridge receives 32-byte ESP-NOW payloads from sensor nodes,
 * prepends the sender's 6-byte MAC, COBS-encodes the 38-byte frame,
 * and ships it over USB serial to the Pi hub.
 */

#ifndef WAGGLE_BRIDGE_CONFIG_H
#define WAGGLE_BRIDGE_CONFIG_H

#include <stdint.h>

// --- Hardware ---
static constexpr uint8_t LED_PIN = 2;  // GPIO2, built-in LED on most ESP32-DevKit boards

// --- Serial ---
static constexpr uint32_t SERIAL_BAUD = 115200;

// --- Payload sizes ---
static constexpr size_t MAC_LEN          = 6;   // ESP-NOW sender MAC
static constexpr size_t PAYLOAD_LEN      = 32;  // Sensor reading payload
static constexpr size_t FRAME_LEN        = MAC_LEN + PAYLOAD_LEN;  // 38 bytes
static constexpr size_t COBS_MAX_OUTPUT  = FRAME_LEN + 1 + 1;  // 40 worst-case COBS overhead + extra margin = 41

// COBS worst-case output for N bytes = N + ceil(N/254) bytes.
// For 38 bytes: 38 + 1 = 39 (max), but we allocate 41 for safety.

// Full wire frame: COBS-encoded data + 0x00 delimiter
static constexpr size_t WIRE_MAX         = COBS_MAX_OUTPUT + 1;  // 42

// --- Frame delimiter ---
static constexpr uint8_t FRAME_DELIMITER = 0x00;

#endif // WAGGLE_BRIDGE_CONFIG_H
