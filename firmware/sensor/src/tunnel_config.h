// Waggle Sensor Node — Bee counter tunnel configuration.
//
// Defines timing constants and pin assignments for the dual IR beam-break
// sensor pairs used in the bee counting tunnel entrance.
// Each lane has two beams: A (outer) and B (inner), spaced 10-15mm apart.

#ifndef TUNNEL_CONFIG_H
#define TUNNEL_CONFIG_H

#include <stdint.h>

// ── Number of counting lanes ──────────────────────────────────────────
#define NUM_CHANNELS 4

// ── Timing constants (milliseconds) ──────────────────────────────────
#define DEBOUNCE_MS        3     // Ignore edges within 3ms of last edge
#define MIN_TRANSIT_MS     5     // Minimum valid transit time (beam A→B or B→A)
#define MAX_TRANSIT_MS     200   // Maximum valid transit time before timeout
#define REFRACTORY_MS      30    // Cooldown after a valid transit detection
#define STUCK_BEAM_MS      2000  // Beam held longer than this → stuck flag

// ── Pin assignments (customize per board) ─────────────────────────────
// Channel 0: GPIO 32 (beam A), GPIO 33 (beam B)
// Channel 1: GPIO 25 (beam A), GPIO 26 (beam B)
// Channel 2: GPIO 14 (beam A), GPIO 12 (beam B)
// Channel 3: GPIO 13 (beam A), GPIO 15 (beam B)
static const uint8_t BEAM_A_PINS[NUM_CHANNELS] = {32, 25, 14, 13};
static const uint8_t BEAM_B_PINS[NUM_CHANNELS] = {33, 26, 12, 15};

#endif // TUNNEL_CONFIG_H
