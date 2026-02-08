/**
 * Waggle Bridge — Configuration constants.
 *
 * The bridge receives ESP-NOW payloads from sensor nodes (32-byte Phase 1
 * or 48-byte Phase 2), prepends the sender's 6-byte MAC, COBS-encodes the
 * frame (38 or 54 bytes), and ships it over USB serial to the Pi hub.
 */

#ifndef WAGGLE_BRIDGE_CONFIG_H
#define WAGGLE_BRIDGE_CONFIG_H

#include <stdint.h>

// --- Hardware ---
static constexpr uint8_t LED_PIN = 2;  // GPIO2, built-in LED on most ESP32-DevKit boards

// --- Serial ---
static constexpr uint32_t SERIAL_BAUD = 115200;

// --- Payload sizes ---
static constexpr size_t MAC_LEN              = 6;   // ESP-NOW sender MAC

// Phase 1: 32-byte sensor payload -> 38-byte frame
static constexpr size_t PAYLOAD_LEN_P1       = 32;
static constexpr size_t FRAME_LEN_P1         = MAC_LEN + PAYLOAD_LEN_P1;  // 38 bytes

// Phase 2: 48-byte bee-counting payload -> 54-byte frame
static constexpr size_t PAYLOAD_LEN_P2       = 48;
static constexpr size_t FRAME_LEN_P2         = MAC_LEN + PAYLOAD_LEN_P2;  // 54 bytes

// Maximum decoded frame size (must hold the largest frame)
static constexpr size_t MAX_DECODED_SIZE     = 64;

// COBS worst-case output for N bytes = N + ceil(N/254) bytes.
// For 64 bytes: 64 + 1 = 65 (max). We allocate 70 for safety.
static constexpr size_t COBS_MAX_OUTPUT      = 70;

// Full wire frame: COBS-encoded data + 0x00 delimiter
static constexpr size_t WIRE_MAX             = COBS_MAX_OUTPUT + 1;  // 71

// --- Frame delimiter ---
static constexpr uint8_t FRAME_DELIMITER = 0x00;

#endif // WAGGLE_BRIDGE_CONFIG_H
