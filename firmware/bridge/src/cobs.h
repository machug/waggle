/**
 * Waggle Bridge — COBS (Consistent Overhead Byte Stuffing) encoder.
 *
 * Encodes arbitrary binary data so that the output contains no zero bytes,
 * allowing 0x00 to be used as an unambiguous frame delimiter on the serial
 * link between the ESP32 bridge and the Pi hub.
 *
 * This implementation MUST produce output identical to the Python encoder
 * in backend/waggle/utils/cobs.py so the Pi can decode frames correctly.
 */

#ifndef WAGGLE_BRIDGE_COBS_H
#define WAGGLE_BRIDGE_COBS_H

#include <stddef.h>
#include <stdint.h>

/**
 * COBS-encode `len` bytes from `input` into `output`.
 *
 * @param input   Source data (may contain zero bytes).
 * @param len     Number of bytes to encode.
 * @param output  Destination buffer. Must be at least (len + ceil(len/254) + 1)
 *                bytes. For the Waggle 38-byte frame, 41 bytes suffices.
 * @return        Number of bytes written to `output` (does NOT include a
 *                trailing 0x00 delimiter — the caller must append that).
 *
 * The encoded output is guaranteed to contain no 0x00 bytes.
 */
size_t cobs_encode(const uint8_t* input, size_t len, uint8_t* output);

#endif // WAGGLE_BRIDGE_COBS_H
