// Waggle Sensor Node — 32-byte payload definition, CRC-8, and builder.
//
// Payload format (little-endian):
//   Offset  Size  Type     Field
//   0       1     uint8    hive_id (1-250)
//   1       1     uint8    msg_type (0x01 = sensor data)
//   2       2     uint16   sequence (0-65535, wraps)
//   4       4     int32    weight_g (signed, grams)
//   8       2     int16    temp_c_x100
//   10      2     uint16   humidity_x100
//   12      2     uint16   pressure_hpa_x10
//   14      2     uint16   battery_mv
//   16      1     uint8    flags
//   17      1     uint8    CRC-8 over bytes 0-16
//   18-31   14    reserved (zeros)

#ifndef PAYLOAD_H
#define PAYLOAD_H

#include <stdint.h>
#include <string.h>

// ── Message types ───────────────────────────────────────────────────
#define MSG_TYPE_SENSOR  0x01

// ── Flag bits ───────────────────────────────────────────────────────
#define FLAG_FIRST_BOOT    (1 << 0)  // Bit 0
#define FLAG_LOW_BATTERY   (1 << 3)  // Bit 3
#define FLAG_HX711_ERROR   (1 << 5)  // Bit 5
#define FLAG_BME280_ERROR  (1 << 6)  // Bit 6

// ── Payload size ────────────────────────────────────────────────────
#define PAYLOAD_SIZE  32

// ── Packed payload struct ───────────────────────────────────────────
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

// ── Build a complete sensor payload ─────────────────────────────────
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

#endif // PAYLOAD_H
