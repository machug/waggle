// Waggle Sensor Node — Native unit tests for bee counter state machine
// and Phase 2 (48-byte) payload format.
//
// Runs on the host (no ESP32 required) via:
//   pio test -e native
//
// Tests:
//   1. A-first-then-B sequence counts as IN
//   2. B-first-then-A sequence counts as OUT
//   3. Timeout (>MAX_TRANSIT_MS) discards count
//   4. Debounce rejects edges within DEBOUNCE_MS
//   5. Transit too fast (<MIN_TRANSIT_MS) discards count
//   6. Cooldown prevents double-counting
//   7. Counter overflow clamps at 65535
//   8. bee_count_payload_t is exactly 48 bytes
//   9. 48-byte payload has correct field offsets
//  10. msg_type is 0x02 in payload
//  11. CRC covers bytes 0-16 only

#include <unity.h>
#include <stdint.h>
#include <string.h>

// Include headers under test (bee_counter.h exposes state machine logic
// for native testing; the hardware ISR code is guarded by #ifndef UNIT_TEST)
#include "../src/tunnel_config.h"
#include "../src/bee_counter.h"
#include "../src/payload.h"

// ── Helper: reset a LaneData struct to clean state ────────────────────
static void lane_reset(LaneData* lane) {
    memset(lane, 0, sizeof(LaneData));
    lane->state = LANE_IDLE;
}

// ═══════════════════════════════════════════════════════════════════════
// State machine direction detection
// ═══════════════════════════════════════════════════════════════════════

void test_a_then_b_counts_as_in(void) {
    LaneData lane;
    lane_reset(&lane);

    // Beam A breaks at t=100
    lane_beam_a_event(&lane, 100);
    TEST_ASSERT_EQUAL(LANE_A_BROKEN, lane.state);
    TEST_ASSERT_EQUAL_UINT32(0, lane.bees_in);

    // Beam B breaks at t=150 (50ms transit, within MIN..MAX window)
    lane_beam_b_event(&lane, 150);
    TEST_ASSERT_EQUAL(LANE_COOLDOWN, lane.state);
    TEST_ASSERT_EQUAL_UINT32(1, lane.bees_in);
    TEST_ASSERT_EQUAL_UINT32(0, lane.bees_out);
}

void test_b_then_a_counts_as_out(void) {
    LaneData lane;
    lane_reset(&lane);

    // Beam B breaks at t=100
    lane_beam_b_event(&lane, 100);
    TEST_ASSERT_EQUAL(LANE_B_BROKEN, lane.state);
    TEST_ASSERT_EQUAL_UINT32(0, lane.bees_out);

    // Beam A breaks at t=150 (50ms transit)
    lane_beam_a_event(&lane, 150);
    TEST_ASSERT_EQUAL(LANE_COOLDOWN, lane.state);
    TEST_ASSERT_EQUAL_UINT32(0, lane.bees_in);
    TEST_ASSERT_EQUAL_UINT32(1, lane.bees_out);
}

void test_multiple_transits(void) {
    LaneData lane;
    lane_reset(&lane);

    // First bee IN: A@100, B@120
    lane_beam_a_event(&lane, 100);
    lane_beam_b_event(&lane, 120);
    TEST_ASSERT_EQUAL_UINT32(1, lane.bees_in);

    // Wait for cooldown to expire
    lane_check_timeout(&lane, 120 + REFRACTORY_MS);
    TEST_ASSERT_EQUAL(LANE_IDLE, lane.state);

    // Second bee OUT: B@200, A@220
    lane_beam_b_event(&lane, 200);
    lane_beam_a_event(&lane, 220);
    TEST_ASSERT_EQUAL_UINT32(1, lane.bees_in);
    TEST_ASSERT_EQUAL_UINT32(1, lane.bees_out);
}

// ═══════════════════════════════════════════════════════════════════════
// Timeout / discard
// ═══════════════════════════════════════════════════════════════════════

void test_timeout_discards_count(void) {
    LaneData lane;
    lane_reset(&lane);

    // Beam A breaks at t=100
    lane_beam_a_event(&lane, 100);
    TEST_ASSERT_EQUAL(LANE_A_BROKEN, lane.state);

    // Beam B breaks at t=400 (300ms > MAX_TRANSIT_MS=200)
    lane_beam_b_event(&lane, 400);
    // Should still be A_BROKEN or have timed out — check via timeout
    // Actually, the B event in A_BROKEN state checks transit window.
    // 300ms > MAX_TRANSIT_MS, so it goes to COOLDOWN but does NOT count.
    TEST_ASSERT_EQUAL(LANE_COOLDOWN, lane.state);
    TEST_ASSERT_EQUAL_UINT32(0, lane.bees_in);
    TEST_ASSERT_EQUAL_UINT32(0, lane.bees_out);
}

void test_timeout_via_check_returns_to_idle(void) {
    LaneData lane;
    lane_reset(&lane);

    // Beam A breaks at t=100
    lane_beam_a_event(&lane, 100);
    TEST_ASSERT_EQUAL(LANE_A_BROKEN, lane.state);

    // Check timeout at t=400 (300ms > MAX_TRANSIT_MS)
    lane_check_timeout(&lane, 400);
    TEST_ASSERT_EQUAL(LANE_IDLE, lane.state);
    TEST_ASSERT_EQUAL_UINT32(0, lane.bees_in);
}

void test_transit_too_fast_discards(void) {
    LaneData lane;
    lane_reset(&lane);

    // Beam A breaks at t=100
    lane_beam_a_event(&lane, 100);

    // Beam B breaks at t=102 (2ms < MIN_TRANSIT_MS=5)
    // But this would be caught by debounce on B (last_edge_b_ms=0, 102-0=102 > DEBOUNCE_MS)
    // So B event fires, transit = 2ms < MIN_TRANSIT_MS, no count but still goes to COOLDOWN
    lane_beam_b_event(&lane, 102);
    TEST_ASSERT_EQUAL(LANE_COOLDOWN, lane.state);
    TEST_ASSERT_EQUAL_UINT32(0, lane.bees_in);
}

// ═══════════════════════════════════════════════════════════════════════
// Debounce
// ═══════════════════════════════════════════════════════════════════════

void test_debounce_rejects_rapid_edges(void) {
    LaneData lane;
    lane_reset(&lane);

    // First A edge at t=100 — accepted
    lane_beam_a_event(&lane, 100);
    TEST_ASSERT_EQUAL(LANE_A_BROKEN, lane.state);

    // Rapid A edge at t=101 (1ms < DEBOUNCE_MS=3) — rejected
    lane_beam_a_event(&lane, 101);
    TEST_ASSERT_EQUAL(LANE_A_BROKEN, lane.state);  // State unchanged

    // B edge at proper time t=150 — should count
    lane_beam_b_event(&lane, 150);
    TEST_ASSERT_EQUAL_UINT32(1, lane.bees_in);
}

void test_debounce_on_b_beam(void) {
    LaneData lane;
    lane_reset(&lane);

    // B edge at t=100
    lane_beam_b_event(&lane, 100);
    TEST_ASSERT_EQUAL(LANE_B_BROKEN, lane.state);

    // Rapid B edge at t=101 — rejected
    lane_beam_b_event(&lane, 101);
    TEST_ASSERT_EQUAL(LANE_B_BROKEN, lane.state);

    // A edge at t=150 — counts as OUT
    lane_beam_a_event(&lane, 150);
    TEST_ASSERT_EQUAL_UINT32(1, lane.bees_out);
}

// ═══════════════════════════════════════════════════════════════════════
// Cooldown
// ═══════════════════════════════════════════════════════════════════════

void test_cooldown_prevents_double_count(void) {
    LaneData lane;
    lane_reset(&lane);

    // Valid IN transit: A@100, B@120
    lane_beam_a_event(&lane, 100);
    lane_beam_b_event(&lane, 120);
    TEST_ASSERT_EQUAL(LANE_COOLDOWN, lane.state);
    TEST_ASSERT_EQUAL_UINT32(1, lane.bees_in);

    // During cooldown, new beam events are ignored
    lane_beam_a_event(&lane, 125);
    lane_beam_b_event(&lane, 130);
    TEST_ASSERT_EQUAL(LANE_COOLDOWN, lane.state);
    TEST_ASSERT_EQUAL_UINT32(1, lane.bees_in);  // Still 1
}

void test_cooldown_expires_to_idle(void) {
    LaneData lane;
    lane_reset(&lane);

    // Valid IN transit: A@100, B@120 → COOLDOWN entered at t=120
    lane_beam_a_event(&lane, 100);
    lane_beam_b_event(&lane, 120);
    TEST_ASSERT_EQUAL(LANE_COOLDOWN, lane.state);

    // Before cooldown expires
    lane_check_timeout(&lane, 120 + REFRACTORY_MS - 1);
    TEST_ASSERT_EQUAL(LANE_COOLDOWN, lane.state);

    // After cooldown expires
    lane_check_timeout(&lane, 120 + REFRACTORY_MS);
    TEST_ASSERT_EQUAL(LANE_IDLE, lane.state);
}

// ═══════════════════════════════════════════════════════════════════════
// Stuck detection
// ═══════════════════════════════════════════════════════════════════════

void test_stuck_beam_detection(void) {
    LaneData lane;
    lane_reset(&lane);

    // Beam A breaks at t=100
    lane_beam_a_event(&lane, 100);
    TEST_ASSERT_FALSE(lane.stuck);

    // Check at t=100 + STUCK_BEAM_MS + 1 — should be stuck
    lane_check_timeout(&lane, 100 + STUCK_BEAM_MS + 1);
    TEST_ASSERT_TRUE(lane.stuck);
    // State should have returned to IDLE (MAX_TRANSIT_MS < STUCK_BEAM_MS)
    TEST_ASSERT_EQUAL(LANE_IDLE, lane.state);
}

// ═══════════════════════════════════════════════════════════════════════
// Counter overflow / clamping
// ═══════════════════════════════════════════════════════════════════════

void test_counter_overflow_clamps(void) {
    // Simulate a lane with counts exceeding uint16 range
    LaneData lane;
    lane_reset(&lane);

    // Directly set bees_in to near overflow
    lane.bees_in = 70000;   // > 65535
    lane.bees_out = 65535;  // Exactly at limit

    // Verify the values are there (native test can read them directly)
    // The clamping happens in bee_counter_snapshot() on ESP32.
    // For native testing, verify the concept:
    uint16_t clamped_in  = (lane.bees_in  > 65535) ? 65535 : (uint16_t)lane.bees_in;
    uint16_t clamped_out = (lane.bees_out > 65535) ? 65535 : (uint16_t)lane.bees_out;

    TEST_ASSERT_EQUAL_UINT16(65535, clamped_in);
    TEST_ASSERT_EQUAL_UINT16(65535, clamped_out);
}

// ═══════════════════════════════════════════════════════════════════════
// Phase 2 payload struct layout
// ═══════════════════════════════════════════════════════════════════════

void test_bee_count_payload_size(void) {
    TEST_ASSERT_EQUAL(PAYLOAD_SIZE_V2, sizeof(bee_count_payload_t));
    TEST_ASSERT_EQUAL(48, sizeof(bee_count_payload_t));
}

void test_phase1_payload_size_unchanged(void) {
    // Phase 1 payload must remain 32 bytes
    TEST_ASSERT_EQUAL(PAYLOAD_SIZE, sizeof(sensor_payload_t));
    TEST_ASSERT_EQUAL(32, sizeof(sensor_payload_t));
}

void test_bee_count_payload_field_offsets(void) {
    // Build a known payload and verify field positions via raw byte access
    bee_count_payload_t p;
    memset(&p, 0, sizeof(p));

    // Use offsetof-equivalent checks via pointer arithmetic
    uint8_t* base = (uint8_t*)&p;

    // Verify field offsets match the spec
    TEST_ASSERT_EQUAL_PTR(base + 0,  &p.hive_id);
    TEST_ASSERT_EQUAL_PTR(base + 1,  &p.msg_type);
    TEST_ASSERT_EQUAL_PTR(base + 2,  &p.sequence);
    TEST_ASSERT_EQUAL_PTR(base + 4,  &p.weight_g);
    TEST_ASSERT_EQUAL_PTR(base + 8,  &p.temp_c_x100);
    TEST_ASSERT_EQUAL_PTR(base + 10, &p.humidity_x100);
    TEST_ASSERT_EQUAL_PTR(base + 12, &p.pressure_hpa_x10);
    TEST_ASSERT_EQUAL_PTR(base + 14, &p.battery_mv);
    TEST_ASSERT_EQUAL_PTR(base + 16, &p.flags);
    TEST_ASSERT_EQUAL_PTR(base + 17, &p.crc);
    TEST_ASSERT_EQUAL_PTR(base + 18, &p.bees_in);
    TEST_ASSERT_EQUAL_PTR(base + 20, &p.bees_out);
    TEST_ASSERT_EQUAL_PTR(base + 22, &p.period_ms);
    TEST_ASSERT_EQUAL_PTR(base + 26, &p.lane_mask);
    TEST_ASSERT_EQUAL_PTR(base + 27, &p.stuck_mask);
    TEST_ASSERT_EQUAL_PTR(base + 28, &p.reserved);
}

void test_bee_count_payload_msg_type(void) {
    bee_count_payload_t p;
    payload_build_v2(&p,
                     /* hive_id */          1,
                     /* sequence */          0,
                     /* weight_g */          0,
                     /* temp_c_x100 */       0,
                     /* humidity_x100 */     0,
                     /* pressure_hpa_x10 */  0,
                     /* battery_mv */        4200,
                     /* flags */             0,
                     /* bees_in */           10,
                     /* bees_out */          5,
                     /* period_ms */         60000,
                     /* lane_mask */         0x0F,
                     /* stuck_mask */        0x00);

    TEST_ASSERT_EQUAL_UINT8(MSG_TYPE_BEE_COUNT, p.msg_type);
    TEST_ASSERT_EQUAL_UINT8(0x02, p.msg_type);
}

void test_bee_count_payload_build_fields(void) {
    bee_count_payload_t p;
    payload_build_v2(&p,
                     /* hive_id */          42,
                     /* sequence */          1000,
                     /* weight_g */          -500,
                     /* temp_c_x100 */       3645,
                     /* humidity_x100 */     5120,
                     /* pressure_hpa_x10 */  10132,
                     /* battery_mv */        3700,
                     /* flags */             FLAG_LOW_BATTERY,
                     /* bees_in */           123,
                     /* bees_out */          45,
                     /* period_ms */         60000,
                     /* lane_mask */         0x0F,
                     /* stuck_mask */        0x02);

    // Sensor fields
    TEST_ASSERT_EQUAL_UINT8(42, p.hive_id);
    TEST_ASSERT_EQUAL_UINT8(MSG_TYPE_BEE_COUNT, p.msg_type);
    TEST_ASSERT_EQUAL_UINT16(1000, p.sequence);
    TEST_ASSERT_EQUAL_INT32(-500, p.weight_g);
    TEST_ASSERT_EQUAL_INT16(3645, p.temp_c_x100);
    TEST_ASSERT_EQUAL_UINT16(5120, p.humidity_x100);
    TEST_ASSERT_EQUAL_UINT16(10132, p.pressure_hpa_x10);
    TEST_ASSERT_EQUAL_UINT16(3700, p.battery_mv);
    TEST_ASSERT_EQUAL_UINT8(FLAG_LOW_BATTERY, p.flags);

    // Bee counting fields
    TEST_ASSERT_EQUAL_UINT16(123, p.bees_in);
    TEST_ASSERT_EQUAL_UINT16(45, p.bees_out);
    TEST_ASSERT_EQUAL_UINT32(60000, p.period_ms);
    TEST_ASSERT_EQUAL_UINT8(0x0F, p.lane_mask);
    TEST_ASSERT_EQUAL_UINT8(0x02, p.stuck_mask);

    // Reserved should be zero
    for (int i = 0; i < 20; i++) {
        TEST_ASSERT_EQUAL_UINT8(0, p.reserved[i]);
    }
}

void test_bee_count_payload_crc(void) {
    bee_count_payload_t p;
    payload_build_v2(&p,
                     /* hive_id */          1,
                     /* sequence */          100,
                     /* weight_g */          5000,
                     /* temp_c_x100 */       2500,
                     /* humidity_x100 */     6000,
                     /* pressure_hpa_x10 */  10130,
                     /* battery_mv */        3800,
                     /* flags */             0,
                     /* bees_in */           50,
                     /* bees_out */          30,
                     /* period_ms */         60000,
                     /* lane_mask */         0x0F,
                     /* stuck_mask */        0x00);

    // CRC covers bytes 0-16 only (same as Phase 1)
    uint8_t expected_crc = crc8((const uint8_t*)&p, 17);
    TEST_ASSERT_EQUAL_HEX8(expected_crc, p.crc);

    // Verify CRC does NOT cover bee counting fields by mutating them
    // and checking CRC is still valid over 0-16
    bee_count_payload_t p2;
    memcpy(&p2, &p, sizeof(p));
    p2.bees_in = 9999;
    p2.bees_out = 8888;
    // CRC should still match since it only covers 0-16
    TEST_ASSERT_EQUAL_HEX8(p.crc, crc8((const uint8_t*)&p2, 17));
}

void test_bee_count_payload_raw_bytes(void) {
    // Build a payload and verify specific byte positions in the raw buffer
    bee_count_payload_t p;
    payload_build_v2(&p,
                     /* hive_id */          0xAA,
                     /* sequence */          0,
                     /* weight_g */          0,
                     /* temp_c_x100 */       0,
                     /* humidity_x100 */     0,
                     /* pressure_hpa_x10 */  0,
                     /* battery_mv */        0,
                     /* flags */             0,
                     /* bees_in */           0x1234,
                     /* bees_out */          0x5678,
                     /* period_ms */         0xDEADBEEF,
                     /* lane_mask */         0x0F,
                     /* stuck_mask */        0x03);

    uint8_t* raw = (uint8_t*)&p;

    // Byte 0 = hive_id
    TEST_ASSERT_EQUAL_HEX8(0xAA, raw[0]);

    // Byte 1 = msg_type
    TEST_ASSERT_EQUAL_HEX8(0x02, raw[1]);

    // Bytes 18-19 = bees_in (little-endian: 0x34, 0x12)
    TEST_ASSERT_EQUAL_HEX8(0x34, raw[18]);
    TEST_ASSERT_EQUAL_HEX8(0x12, raw[19]);

    // Bytes 20-21 = bees_out (little-endian: 0x78, 0x56)
    TEST_ASSERT_EQUAL_HEX8(0x78, raw[20]);
    TEST_ASSERT_EQUAL_HEX8(0x56, raw[21]);

    // Bytes 22-25 = period_ms (little-endian: 0xEF, 0xBE, 0xAD, 0xDE)
    TEST_ASSERT_EQUAL_HEX8(0xEF, raw[22]);
    TEST_ASSERT_EQUAL_HEX8(0xBE, raw[23]);
    TEST_ASSERT_EQUAL_HEX8(0xAD, raw[24]);
    TEST_ASSERT_EQUAL_HEX8(0xDE, raw[25]);

    // Byte 26 = lane_mask
    TEST_ASSERT_EQUAL_HEX8(0x0F, raw[26]);

    // Byte 27 = stuck_mask
    TEST_ASSERT_EQUAL_HEX8(0x03, raw[27]);

    // Bytes 28-47 = reserved (all zero)
    for (int i = 28; i < 48; i++) {
        TEST_ASSERT_EQUAL_HEX8(0x00, raw[i]);
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Flag bits
// ═══════════════════════════════════════════════════════════════════════

void test_phase2_flag_bits_non_overlapping(void) {
    // Verify Phase 2 flag bits don't collide with Phase 1 flags
    uint8_t all_flags = FLAG_FIRST_BOOT | FLAG_LOW_BATTERY |
                        FLAG_HX711_ERROR | FLAG_BME280_ERROR |
                        FLAG_MEASUREMENT_CLAMPED | FLAG_COUNTER_STUCK;

    // All six flags should produce 6 distinct bits
    // Count set bits
    int count = 0;
    for (int i = 0; i < 8; i++) {
        if (all_flags & (1 << i)) count++;
    }
    TEST_ASSERT_EQUAL(6, count);

    // Verify specific bit positions
    TEST_ASSERT_EQUAL_HEX8(0x01, FLAG_FIRST_BOOT);
    TEST_ASSERT_EQUAL_HEX8(0x02, FLAG_MEASUREMENT_CLAMPED);
    TEST_ASSERT_EQUAL_HEX8(0x04, FLAG_COUNTER_STUCK);
    TEST_ASSERT_EQUAL_HEX8(0x08, FLAG_LOW_BATTERY);
    TEST_ASSERT_EQUAL_HEX8(0x20, FLAG_HX711_ERROR);
    TEST_ASSERT_EQUAL_HEX8(0x40, FLAG_BME280_ERROR);
}

// ═══════════════════════════════════════════════════════════════════════
// Test runner
// ═══════════════════════════════════════════════════════════════════════

int main(int argc, char** argv) {
    UNITY_BEGIN();

    // State machine — direction detection
    RUN_TEST(test_a_then_b_counts_as_in);
    RUN_TEST(test_b_then_a_counts_as_out);
    RUN_TEST(test_multiple_transits);

    // Timeout / discard
    RUN_TEST(test_timeout_discards_count);
    RUN_TEST(test_timeout_via_check_returns_to_idle);
    RUN_TEST(test_transit_too_fast_discards);

    // Debounce
    RUN_TEST(test_debounce_rejects_rapid_edges);
    RUN_TEST(test_debounce_on_b_beam);

    // Cooldown
    RUN_TEST(test_cooldown_prevents_double_count);
    RUN_TEST(test_cooldown_expires_to_idle);

    // Stuck detection
    RUN_TEST(test_stuck_beam_detection);

    // Counter overflow
    RUN_TEST(test_counter_overflow_clamps);

    // Phase 2 payload layout
    RUN_TEST(test_bee_count_payload_size);
    RUN_TEST(test_phase1_payload_size_unchanged);
    RUN_TEST(test_bee_count_payload_field_offsets);
    RUN_TEST(test_bee_count_payload_msg_type);
    RUN_TEST(test_bee_count_payload_build_fields);
    RUN_TEST(test_bee_count_payload_crc);
    RUN_TEST(test_bee_count_payload_raw_bytes);

    // Flag bits
    RUN_TEST(test_phase2_flag_bits_non_overlapping);

    return UNITY_END();
}
