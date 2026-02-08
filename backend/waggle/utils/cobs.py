"""COBS (Consistent Overhead Byte Stuffing) encoder/decoder."""


class CobsDecodeError(Exception):
    pass


def cobs_encode(data: bytes) -> bytes:
    """Encode data using COBS. Does NOT append a 0x00 delimiter.

    COBS encoding replaces all zero bytes with overhead codes that indicate
    the distance to the next zero (or end of data). This guarantees the
    encoded output contains no zero bytes, making 0x00 safe as a frame
    delimiter.

    Algorithm:
    - Walk the input, collecting runs of non-zero bytes.
    - Each run is preceded by a code byte: code = len(run) + 1.
    - If the run ends because a zero was found, that zero is implicit
      (reconstructed during decode) and consumed.
    - If the run reaches 254 bytes without hitting a zero, emit code 0xFF
      followed by the 254 bytes, and continue WITHOUT inserting an implicit
      zero.
    """
    output = bytearray()
    idx = 0
    length = len(data)

    # We need to process one "block" per iteration. After consuming a trailing
    # zero, idx == length but we still need to emit a final overhead byte, so
    # we track whether we should continue via a flag.
    need_final = True

    while idx < length:
        # Find the next zero byte, but cap the run at 254 bytes
        run_start = idx
        while idx < length and data[idx] != 0 and (idx - run_start) < 254:
            idx += 1

        run_length = idx - run_start

        if run_length == 254:
            # Max block: 254 non-zero bytes, code = 0xFF, no implicit zero
            output.append(0xFF)
            output.extend(data[run_start:idx])
            # If this was the end of data, no final overhead needed
            need_final = idx < length
        elif idx < length and data[idx] == 0:
            # Run ended by a zero byte: code = run_length + 1, consume the zero
            output.append(run_length + 1)
            output.extend(data[run_start:idx])
            idx += 1  # skip the zero
            # If that zero was the last byte, we still need a final overhead
            need_final = True
        else:
            # End of data: code = run_length + 1
            output.append(run_length + 1)
            output.extend(data[run_start:idx])
            need_final = False

    # If data ended with a zero (or was empty), emit final overhead byte
    if need_final:
        output.append(0x01)

    return bytes(output)


def cobs_decode(data: bytes) -> bytes:
    """Decode COBS-encoded data. Input should NOT include trailing 0x00 delimiter.

    Raises CobsDecodeError on malformed input (empty, embedded zeros, truncated).
    """
    if not data:
        raise CobsDecodeError("Empty COBS frame")

    output = bytearray()
    idx = 0
    length = len(data)

    while idx < length:
        code = data[idx]
        idx += 1

        if code == 0:
            raise CobsDecodeError("Unexpected zero byte in COBS data")

        # Copy (code - 1) data bytes
        n_data = code - 1
        end = idx + n_data
        if end > length:
            raise CobsDecodeError("COBS frame truncated")

        output.extend(data[idx:end])
        idx = end

        # If code < 0xFF and we haven't reached the end, append an implicit zero
        if code < 0xFF and idx < length:
            output.append(0)

    return bytes(output)
