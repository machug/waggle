// Waggle Sensor Node — ESP-NOW communication layer.
// Initialises Wi-Fi in station mode, registers the bridge peer, and
// provides a send function with retry logic.

#ifndef COMMS_H
#define COMMS_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

// Initialise ESP-NOW and register the bridge as a peer.
// bridge_mac must point to a 6-byte MAC address.
// Returns true on success.
bool comms_init(const uint8_t* bridge_mac);

// Send `len` bytes to the bridge.  Retries up to ESPNOW_MAX_RETRIES
// times with ESPNOW_RETRY_MS delay between attempts.
// Returns true if delivery was acknowledged.
bool comms_send(const uint8_t* data, size_t len);

#endif // COMMS_H
