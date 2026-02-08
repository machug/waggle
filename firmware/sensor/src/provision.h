// Waggle Sensor Node — Provisioning mode.
// When GPIO27 is held LOW at boot, the node enters an interactive serial
// console for configuration (hive ID, bridge MAC, tare, calibration).
// All values are persisted to NVS.

#ifndef PROVISION_H
#define PROVISION_H

#include <stdint.h>

// Load persisted configuration from NVS into module-level state.
// Must be called early in setup() before sensors_init() or comms_init().
// Populates hive_id, bridge_mac, hx711_scale_factor, hx711_offset.
void provision_load();

// Check GPIO27.  If LOW, enters the provisioning serial loop and never
// returns (the user must REBOOT to exit).  If HIGH, returns immediately.
void provision_check();

// Read-only accessors for provisioned values.
uint8_t  provision_hive_id();
const uint8_t* provision_bridge_mac();
bool     provision_is_configured();  // hive_id != 0 && bridge_mac set

#endif // PROVISION_H
