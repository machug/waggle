// Waggle Sensor Node — Bee counter ISR module implementation.
//
// Each lane runs an independent state machine driven by beam-break
// interrupts.  The state machine logic (lane_beam_a_event,
// lane_beam_b_event, lane_check_timeout) is separated from the
// ISR/GPIO glue so it can be tested natively.

#include "bee_counter.h"
#include "tunnel_config.h"

// ── Pure state machine logic (testable on any platform) ───────────────

void lane_beam_a_event(LaneData* lane, uint32_t now_ms) {
    // Debounce: ignore if too soon after last A edge
    if ((now_ms - lane->last_edge_a_ms) < DEBOUNCE_MS) {
        return;
    }
    lane->last_edge_a_ms = now_ms;

    switch (lane->state) {
        case LANE_IDLE:
            // Beam A broken first — potential inbound bee
            lane->state = LANE_A_BROKEN;
            lane->state_enter_ms = now_ms;
            break;

        case LANE_B_BROKEN: {
            // B broke first, now A broke — bee leaving (OUT)
            uint32_t transit = now_ms - lane->state_enter_ms;
            if (transit >= MIN_TRANSIT_MS && transit <= MAX_TRANSIT_MS) {
                lane->bees_out++;
            }
            // Regardless of validity, go to cooldown
            lane->state = LANE_COOLDOWN;
            lane->state_enter_ms = now_ms;
            break;
        }

        case LANE_A_BROKEN:
        case LANE_COOLDOWN:
            // Ignore: duplicate A event or in cooldown
            break;
    }
}

void lane_beam_b_event(LaneData* lane, uint32_t now_ms) {
    // Debounce: ignore if too soon after last B edge
    if ((now_ms - lane->last_edge_b_ms) < DEBOUNCE_MS) {
        return;
    }
    lane->last_edge_b_ms = now_ms;

    switch (lane->state) {
        case LANE_IDLE:
            // Beam B broken first — potential outbound bee
            lane->state = LANE_B_BROKEN;
            lane->state_enter_ms = now_ms;
            break;

        case LANE_A_BROKEN: {
            // A broke first, now B broke — bee entering (IN)
            uint32_t transit = now_ms - lane->state_enter_ms;
            if (transit >= MIN_TRANSIT_MS && transit <= MAX_TRANSIT_MS) {
                lane->bees_in++;
            }
            // Regardless of validity, go to cooldown
            lane->state = LANE_COOLDOWN;
            lane->state_enter_ms = now_ms;
            break;
        }

        case LANE_B_BROKEN:
        case LANE_COOLDOWN:
            // Ignore: duplicate B event or in cooldown
            break;
    }
}

void lane_check_timeout(LaneData* lane, uint32_t now_ms) {
    uint32_t elapsed = now_ms - lane->state_enter_ms;

    switch (lane->state) {
        case LANE_A_BROKEN:
        case LANE_B_BROKEN:
            // Waiting for second beam — check for timeout
            if (elapsed > MAX_TRANSIT_MS) {
                lane->state = LANE_IDLE;
            }
            // Check for stuck beam
            if (elapsed > STUCK_BEAM_MS) {
                lane->stuck = true;
            }
            break;

        case LANE_COOLDOWN:
            // Refractory period elapsed — return to idle
            if (elapsed >= REFRACTORY_MS) {
                lane->state = LANE_IDLE;
            }
            break;

        case LANE_IDLE:
            // Nothing to do
            break;
    }
}

// ── Hardware-specific ISR and GPIO code (ESP32 only) ──────────────────
#ifndef UNIT_TEST

#include <Arduino.h>
#include <esp_attr.h>

// Module state
static LaneData s_lanes[NUM_CHANNELS];
static uint8_t  s_lane_mask = 0;
static uint32_t s_last_snapshot_ms = 0;
static portMUX_TYPE s_mux = portMUX_INITIALIZER_UNLOCKED;

// ── ISR handlers (one pair per lane, generated with macros) ───────────
// Each beam gets its own ISR that reads the pin state and calls the
// state machine transition function.  IRAM_ATTR keeps the ISR in
// fast internal RAM.

#define DEFINE_ISR_A(ch)                                         \
    static void IRAM_ATTR isr_beam_a_##ch() {                   \
        if (digitalRead(BEAM_A_PINS[ch]) == LOW) {               \
            portENTER_CRITICAL_ISR(&s_mux);                      \
            lane_beam_a_event(&s_lanes[ch], millis());           \
            portEXIT_CRITICAL_ISR(&s_mux);                       \
        }                                                        \
    }

#define DEFINE_ISR_B(ch)                                         \
    static void IRAM_ATTR isr_beam_b_##ch() {                   \
        if (digitalRead(BEAM_B_PINS[ch]) == LOW) {               \
            portENTER_CRITICAL_ISR(&s_mux);                      \
            lane_beam_b_event(&s_lanes[ch], millis());           \
            portEXIT_CRITICAL_ISR(&s_mux);                       \
        }                                                        \
    }

DEFINE_ISR_A(0)
DEFINE_ISR_A(1)
DEFINE_ISR_A(2)
DEFINE_ISR_A(3)

DEFINE_ISR_B(0)
DEFINE_ISR_B(1)
DEFINE_ISR_B(2)
DEFINE_ISR_B(3)

// ISR function pointer arrays for dynamic attachment
static void (*const s_isr_a[NUM_CHANNELS])() = {
    isr_beam_a_0, isr_beam_a_1, isr_beam_a_2, isr_beam_a_3
};
static void (*const s_isr_b[NUM_CHANNELS])() = {
    isr_beam_b_0, isr_beam_b_1, isr_beam_b_2, isr_beam_b_3
};

void bee_counter_init(uint8_t lane_mask) {
    s_lane_mask = lane_mask;
    s_last_snapshot_ms = millis();

    for (int ch = 0; ch < NUM_CHANNELS; ch++) {
        // Zero-init lane data
        memset(&s_lanes[ch], 0, sizeof(LaneData));
        s_lanes[ch].state = LANE_IDLE;

        if (!(lane_mask & (1 << ch))) {
            continue;  // Lane not enabled
        }

        // Configure pins as input with pull-up (beam break = active LOW)
        pinMode(BEAM_A_PINS[ch], INPUT_PULLUP);
        pinMode(BEAM_B_PINS[ch], INPUT_PULLUP);

        // Attach interrupts on FALLING edge (beam broken)
        attachInterrupt(digitalPinToInterrupt(BEAM_A_PINS[ch]),
                        s_isr_a[ch], FALLING);
        attachInterrupt(digitalPinToInterrupt(BEAM_B_PINS[ch]),
                        s_isr_b[ch], FALLING);
    }
}

void bee_counter_deinit() {
    for (int ch = 0; ch < NUM_CHANNELS; ch++) {
        if (s_lane_mask & (1 << ch)) {
            detachInterrupt(digitalPinToInterrupt(BEAM_A_PINS[ch]));
            detachInterrupt(digitalPinToInterrupt(BEAM_B_PINS[ch]));
        }
    }
    s_lane_mask = 0;
}

BeeCountSnapshot bee_counter_snapshot() {
    BeeCountSnapshot snap;
    uint32_t now = millis();

    portENTER_CRITICAL(&s_mux);

    snap.bees_in  = 0;
    snap.bees_out = 0;
    snap.stuck_mask = 0;

    for (int ch = 0; ch < NUM_CHANNELS; ch++) {
        if (!(s_lane_mask & (1 << ch))) {
            continue;
        }

        // Check for timeouts / stuck beams while in critical section
        lane_check_timeout(&s_lanes[ch], now);

        // Accumulate counters (clamping handled below)
        uint32_t in_count  = s_lanes[ch].bees_in;
        uint32_t out_count = s_lanes[ch].bees_out;

        // Reset ISR counters
        s_lanes[ch].bees_in  = 0;
        s_lanes[ch].bees_out = 0;

        // Accumulate (may exceed uint16 range; clamped below)
        snap.bees_in  += (in_count  > 65535) ? 65535 : (uint16_t)in_count;
        snap.bees_out += (out_count > 65535) ? 65535 : (uint16_t)out_count;

        if (s_lanes[ch].stuck) {
            snap.stuck_mask |= (1 << ch);
            s_lanes[ch].stuck = false;  // Clear after reporting
        }
    }

    snap.period_ms = now - s_last_snapshot_ms;
    s_last_snapshot_ms = now;
    snap.lane_mask = s_lane_mask;

    portEXIT_CRITICAL(&s_mux);

    // Clamp total to uint16 range
    if (snap.bees_in > 65535) {
        snap.bees_in = 65535;
    }
    if (snap.bees_out > 65535) {
        snap.bees_out = 65535;
    }

    return snap;
}

#endif // UNIT_TEST
