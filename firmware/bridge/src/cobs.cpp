/**
 * Waggle Bridge — COBS encoder implementation.
 *
 * Algorithm:
 *   Walk the input, collecting runs of non-zero bytes. Each run is preceded
 *   by a "code" byte equal to (run_length + 1). When a zero is encountered,
 *   the zero itself is consumed (it will be reconstructed by the decoder as
 *   an implicit zero). If a run reaches 254 non-zero bytes (code would be
 *   0xFF), the block is flushed WITHOUT an implicit zero.
 *
 * This matches the Python encoder in backend/waggle/utils/cobs.py exactly.
 */

#include "cobs.h"

size_t cobs_encode(const uint8_t* input, size_t len, uint8_t* output) {
    size_t write_idx = 0;
    size_t code_idx  = 0;
    uint8_t code     = 1;
    bool need_final  = true;  // Whether a final code byte is needed

    write_idx++;  // Reserve space for the first code byte

    for (size_t i = 0; i < len; i++) {
        if (input[i] == 0) {
            // End of run — write the distance code, start a new block
            output[code_idx] = code;
            code_idx = write_idx++;
            code = 1;
            need_final = true;
        } else {
            output[write_idx++] = input[i];
            code++;
            if (code == 0xFF) {
                // Max block (254 non-zero data bytes) — flush without implicit zero
                output[code_idx] = code;
                code_idx = write_idx++;
                code = 1;
                // Only need a final byte if there's more data to process
                need_final = (i + 1) < len;
            }
        }
    }

    // Write the final code byte (unless we just flushed a 0xFF block at end of data)
    if (need_final) {
        output[code_idx] = code;
    } else {
        // Reclaim the space reserved for the unused code byte
        write_idx--;
    }

    return write_idx;
}
