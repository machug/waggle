// Waggle Sensor Node — Native unit tests for payload.h
//
// Runs on the host (no ESP32 required) via:
//   pio test -e native
//
// Tests:
//   1. CRC-8 matches the Python reference (test vector "123456789" -> 0xF4)
//   2. CRC-8 edge cases (empty, single byte, all zeros)
//   3. sensor_payload_t is exactly 32 bytes
//   4. payload_build fills all fields correctly
//   5. CRC in built payload matches manual calculation

#include <unity.h>
#include <stdint.h>
#include <string.h>

// Include the header under test.  It is header-only (inline functions).
#include "../src/payload.h"

// ── CRC-8 tests ─────────────────────────────────────────────────────

void test_crc8_reference_vector(void) {
    // Standard test vector: CRC-8/SMBUS of "123456789" == 0xF4
    const uint8_t data[] = "123456789";
    uint8_t result = crc8(data, 9);
    TEST_ASSERT_EQUAL_HEX8(0xF4, result);
}

void test_crc8_empty(void) {
    uint8_t result = crc8(NULL, 0);
    TEST_ASSERT_EQUAL_HEX8(0x00, result);
}

void test_crc8_single_byte_zero(void) {
    uint8_t data[] = {0x00};
    uint8_t result = crc8(data, 1);
    TEST_ASSERT_EQUAL_HEX8(0x00, result);
}

void test_crc8_single_byte_nonzero(void) {
    uint8_t data[] = {0x01};
    uint8_t result = crc8(data, 1);
    TEST_ASSERT_EQUAL_HEX8(0x07, result);
}

void test_crc8_all_ff(void) {
    uint8_t data[] = {0xFF, 0xFF, 0xFF, 0xFF};
    uint8_t result = crc8(data, 4);
    // CRC-8/SMBUS of {FF,FF,FF,FF} = 0xDE (verified against reference impl)
    TEST_ASSERT_EQUAL_HEX8(0xDE, result);
}

// ── Struct size test ────────────────────────────────────────────────

void test_payload_struct_size(void) {
    TEST_ASSERT_EQUAL(PAYLOAD_SIZE, sizeof(sensor_payload_t));
    TEST_ASSERT_EQUAL(32, sizeof(sensor_payload_t));
}

// ── Payload build tests ─────────────────────────────────────────────

void test_payload_build_fields(void) {
    sensor_payload_t p;
    payload_build(&p,
                  /* hive_id */         42,
                  /* sequence */        1000,
                  /* weight_g */        -500,
                  /* temp_c_x100 */     3645,
                  /* humidity_x100 */   5120,
                  /* pressure_hpa_x10 */10132,
                  /* battery_mv */      3700,
                  /* flags */           0x00);

    TEST_ASSERT_EQUAL_UINT8(42, p.hive_id);
    TEST_ASSERT_EQUAL_UINT8(MSG_TYPE_SENSOR, p.msg_type);
    TEST_ASSERT_EQUAL_UINT16(1000, p.sequence);
    TEST_ASSERT_EQUAL_INT32(-500, p.weight_g);
    TEST_ASSERT_EQUAL_INT16(3645, p.temp_c_x100);
    TEST_ASSERT_EQUAL_UINT16(5120, p.humidity_x100);
    TEST_ASSERT_EQUAL_UINT16(10132, p.pressure_hpa_x10);
    TEST_ASSERT_EQUAL_UINT16(3700, p.battery_mv);
    TEST_ASSERT_EQUAL_UINT8(0x00, p.flags);

    // Reserved bytes should be zero
    for (int i = 0; i < 14; i++) {
        TEST_ASSERT_EQUAL_UINT8(0, p.reserved[i]);
    }
}

void test_payload_build_crc_matches_manual(void) {
    sensor_payload_t p;
    payload_build(&p, 1, 0, 0, 0, 0, 0, 4200, FLAG_FIRST_BOOT);

    // Manually compute CRC over bytes 0..16
    uint8_t expected_crc = crc8((const uint8_t*)&p, 17);
    TEST_ASSERT_EQUAL_HEX8(expected_crc, p.crc);
}

void test_payload_build_flags_preserved(void) {
    sensor_payload_t p;
    uint8_t flags = FLAG_FIRST_BOOT | FLAG_LOW_BATTERY | FLAG_HX711_ERROR;
    payload_build(&p, 10, 65535, 12345, -1000, 9900, 9800, 3100, flags);

    TEST_ASSERT_EQUAL_UINT8(flags, p.flags);
    TEST_ASSERT_BITS(FLAG_FIRST_BOOT, FLAG_FIRST_BOOT, p.flags);
    TEST_ASSERT_BITS(FLAG_LOW_BATTERY, FLAG_LOW_BATTERY, p.flags);
    TEST_ASSERT_BITS(FLAG_HX711_ERROR, FLAG_HX711_ERROR, p.flags);
    TEST_ASSERT_BITS(FLAG_BME280_ERROR, 0, p.flags);  // NOT set
}

void test_payload_build_sequence_wrap(void) {
    sensor_payload_t p;
    payload_build(&p, 1, 65535, 0, 0, 0, 0, 4200, 0);
    TEST_ASSERT_EQUAL_UINT16(65535, p.sequence);
}

void test_payload_build_negative_weight(void) {
    sensor_payload_t p;
    payload_build(&p, 1, 0, -2147483647, 0, 0, 0, 4200, 0);
    TEST_ASSERT_EQUAL_INT32(-2147483647, p.weight_g);
}

// ── Test runner ─────────────────────────────────────────────────────

int main(int argc, char** argv) {
    UNITY_BEGIN();

    // CRC-8 tests
    RUN_TEST(test_crc8_reference_vector);
    RUN_TEST(test_crc8_empty);
    RUN_TEST(test_crc8_single_byte_zero);
    RUN_TEST(test_crc8_single_byte_nonzero);
    RUN_TEST(test_crc8_all_ff);

    // Struct layout
    RUN_TEST(test_payload_struct_size);

    // Payload builder
    RUN_TEST(test_payload_build_fields);
    RUN_TEST(test_payload_build_crc_matches_manual);
    RUN_TEST(test_payload_build_flags_preserved);
    RUN_TEST(test_payload_build_sequence_wrap);
    RUN_TEST(test_payload_build_negative_weight);

    return UNITY_END();
}
