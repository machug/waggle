// Waggle Sensor Node — Payload definitions, CRC-8, and builders.
//
// Phase 1: 32-byte sensor payload (msg_type 0x01)
// Phase 2: 48-byte bee-counting payload (msg_type 0x02)
//
// Phase 2 payload format (little-endian):
//   Offset  Size  Type     Field
//   0       1     uint8    hive_id (1-250)
//   1       1     uint8    msg_type (0x02 = sensor + bee count)
//   2       2     uint16   sequence (0-65535, wraps)
//   4       4     int32    weight_g (signed, grams)
//   8       2     int16    temp_c_x100
//   10      2     uint16   humidity_x100
//   12      2     uint16   pressure_hpa_x10
//   14      2     uint16   battery_mv
//   16      1     uint8    flags
//   17      1     uint8    CRC-8 over bytes 0-16
//   18      2     uint16   bees_in (LE)
//   20      2     uint16   bees_out (LE)
//   22      4     uint32   period_ms (LE)
//   26      1     uint8    lane_mask
//   27      1     uint8    stuck_mask
//   28-47   20    reserved (zeros)

#ifndef PAYLOAD_H
#define PAYLOAD_H

#include <stdint.h>
#include <string.h>

// ── Message types ───────────────────────────────────────────────────
#define MSG_TYPE_SENSOR      0x01
#define MSG_TYPE_BEE_COUNT   0x02

// ── Flag bits ───────────────────────────────────────────────────────
#define FLAG_FIRST_BOOT          (1 << 0)  // Bit 0
#define FLAG_LOW_BATTERY         (1 << 3)  // Bit 3
#define FLAG_HX711_ERROR         (1 << 5)  // Bit 5
#define FLAG_BME280_ERROR        (1 << 6)  // Bit 6
// Phase 2 flag bits (shared flag byte, non-overlapping)
#define FLAG_MEASUREMENT_CLAMPED (1 << 1)  // Bit 1 — bee count clamped at 65535
#define FLAG_COUNTER_STUCK       (1 << 2)  // Bit 2 — one or more beam-break lanes stuck

// ── Payload sizes ─────────────────────────────────────────────────────
#define PAYLOAD_SIZE       32   // Phase 1: sensor only
#define PAYLOAD_SIZE_V2    48   // Phase 2: sensor + bee counting

// ── Packed payload struct (Phase 1 — 32 bytes) ───────────────────────
// Packed to guarantee the exact binary layout on all compilers.
#pragma pack(push, 1)
typedef struct {
    uint8_t  hive_id;           // 0
    uint8_t  msg_type;          // 1
    uint16_t sequence;          // 2-3
    int32_t  weight_g;          // 4-7
    int16_t  temp_c_x100;      // 8-9
    uint16_t humidity_x100;     // 10-11
    uint16_t pressure_hpa_x10; // 12-13
    uint16_t battery_mv;        // 14-15
    uint8_t  flags;             // 16
    uint8_t  crc;               // 17
    uint8_t  reserved[14];      // 18-31
} sensor_payload_t;
#pragma pack(pop)

// ── Packed payload struct (Phase 2 — 48 bytes) ───────────────────────
#pragma pack(push, 1)
typedef struct {
    // Bytes 0-17: identical to Phase 1 core fields
    uint8_t  hive_id;           // 0
    uint8_t  msg_type;          // 1  (0x02 for bee count)
    uint16_t sequence;          // 2-3
    int32_t  weight_g;          // 4-7
    int16_t  temp_c_x100;      // 8-9
    uint16_t humidity_x100;     // 10-11
    uint16_t pressure_hpa_x10; // 12-13
    uint16_t battery_mv;        // 14-15
    uint8_t  flags;             // 16
    uint8_t  crc;               // 17  (CRC-8 over bytes 0-16)
    // Bytes 18-27: bee counting fields
    uint16_t bees_in;           // 18-19
    uint16_t bees_out;          // 20-21
    uint32_t period_ms;         // 22-25
    uint8_t  lane_mask;         // 26
    uint8_t  stuck_mask;        // 27
    // Bytes 28-47: reserved
    uint8_t  reserved[20];      // 28-47
} bee_count_payload_t;
#pragma pack(pop)

// ── CRC-8 (poly 0x07, init 0x00) ───────────────────────────────────
// Matches the Python reference implementation.
// Test vector: crc8((uint8_t*)"123456789", 9) == 0xF4
inline uint8_t crc8(const uint8_t* data, size_t len) {
    uint8_t crc = 0x00;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (uint8_t j = 0; j < 8; j++) {
            if (crc & 0x80)
                crc = (crc << 1) ^ 0x07;
            else
                crc = crc << 1;
        }
    }
    return crc;
}

// ── Build a complete Phase 1 sensor payload (32 bytes) ───────────────
// Populates every field and computes the CRC.  Zeroes reserved bytes.
inline void payload_build(sensor_payload_t* p,
                          uint8_t  hive_id,
                          uint16_t sequence,
                          int32_t  weight_g,
                          int16_t  temp_c_x100,
                          uint16_t humidity_x100,
                          uint16_t pressure_hpa_x10,
                          uint16_t battery_mv,
                          uint8_t  flags)
{
    memset(p, 0, sizeof(sensor_payload_t));
    p->hive_id           = hive_id;
    p->msg_type          = MSG_TYPE_SENSOR;
    p->sequence          = sequence;
    p->weight_g          = weight_g;
    p->temp_c_x100      = temp_c_x100;
    p->humidity_x100     = humidity_x100;
    p->pressure_hpa_x10 = pressure_hpa_x10;
    p->battery_mv        = battery_mv;
    p->flags             = flags;
    // CRC over bytes 0-16 (everything before the crc field itself)
    p->crc = crc8((const uint8_t*)p, 17);
}

// ── Build a complete Phase 2 bee-counting payload (48 bytes) ─────────
// Populates sensor fields, bee count fields, and computes CRC.
inline void payload_build_v2(bee_count_payload_t* p,
                             uint8_t  hive_id,
                             uint16_t sequence,
                             int32_t  weight_g,
                             int16_t  temp_c_x100,
                             uint16_t humidity_x100,
                             uint16_t pressure_hpa_x10,
                             uint16_t battery_mv,
                             uint8_t  flags,
                             uint16_t bees_in,
                             uint16_t bees_out,
                             uint32_t period_ms,
                             uint8_t  lane_mask,
                             uint8_t  stuck_mask)
{
    memset(p, 0, sizeof(bee_count_payload_t));
    p->hive_id           = hive_id;
    p->msg_type          = MSG_TYPE_BEE_COUNT;
    p->sequence          = sequence;
    p->weight_g          = weight_g;
    p->temp_c_x100      = temp_c_x100;
    p->humidity_x100     = humidity_x100;
    p->pressure_hpa_x10 = pressure_hpa_x10;
    p->battery_mv        = battery_mv;
    p->flags             = flags;
    // CRC over bytes 0-16 (same as Phase 1)
    p->crc = crc8((const uint8_t*)p, 17);
    // Bee counting fields
    p->bees_in           = bees_in;
    p->bees_out          = bees_out;
    p->period_ms         = period_ms;
    p->lane_mask         = lane_mask;
    p->stuck_mask        = stuck_mask;
}

#endif // PAYLOAD_H
