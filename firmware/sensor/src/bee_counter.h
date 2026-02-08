// Waggle Sensor Node — Bee counter ISR module interface.
//
// Counts bees entering and leaving the hive using dual IR beam-break
// sensor pairs in a tunnel entrance.  Each lane has two beams
// (A = outer, B = inner) spaced 10-15mm apart.
//
// Direction detection:
//   A breaks first, then B  →  bee entering (bees_in++)
//   B breaks first, then A  →  bee leaving  (bees_out++)
//
// ISR-driven: counters are incremented in interrupt context.
// Call bee_counter_snapshot() to atomically read and reset.

#ifndef BEE_COUNTER_H
#define BEE_COUNTER_H

#include <stdint.h>

// ── Snapshot returned by bee_counter_snapshot() ────────────────────────
struct BeeCountSnapshot {
    uint16_t bees_in;       // Bees that entered during this period
    uint16_t bees_out;      // Bees that left during this period
    uint32_t period_ms;     // Duration of this counting period
    uint8_t  lane_mask;     // Which lanes are active (bitmask)
    uint8_t  stuck_mask;    // Which lanes have stuck beams (bitmask)
};

// ── Lane state machine (exposed for testability) ──────────────────────
enum LaneState : uint8_t {
    LANE_IDLE     = 0,
    LANE_A_BROKEN = 1,
    LANE_B_BROKEN = 2,
    LANE_COOLDOWN = 3
};

// Per-lane data structure.  Volatile qualifiers for ISR-modified fields
// are applied in the actual implementation; this struct definition is
// also used by native tests without volatile.
struct LaneData {
    LaneState state;
    uint32_t  state_enter_ms;
    uint32_t  last_edge_a_ms;    // Last edge time on beam A (for debounce)
    uint32_t  last_edge_b_ms;    // Last edge time on beam B (for debounce)
    uint32_t  bees_in;           // ISR-incremented
    uint32_t  bees_out;          // ISR-incremented
    bool      stuck;             // Beam held > STUCK_BEAM_MS
};

// ── State machine transition (pure logic, no GPIO) ────────────────────
// These functions implement the core direction detection logic.
// They are separated from ISR/GPIO code so native tests can exercise them.
//
// beam_a_event: call when beam A transitions to broken (active LOW).
// beam_b_event: call when beam B transitions to broken (active LOW).
// now_ms:       current time in milliseconds.
void lane_beam_a_event(LaneData* lane, uint32_t now_ms);
void lane_beam_b_event(LaneData* lane, uint32_t now_ms);

// Check for timeout/stuck conditions.  Call periodically from main loop.
void lane_check_timeout(LaneData* lane, uint32_t now_ms);

// ── Hardware interface (not available in native tests) ────────────────
#ifndef UNIT_TEST

void bee_counter_init(uint8_t lane_mask);
void bee_counter_deinit();
BeeCountSnapshot bee_counter_snapshot();

#endif // UNIT_TEST

#endif // BEE_COUNTER_H
