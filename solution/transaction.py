import struct


def varint(n):
    """Bitcoin-style variable length integer encoding."""
    if n < 0xFD:
        return struct.pack("<B", n)
    elif n <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", n)
    elif n <= 0xFFFFFFFF:
        return b"\xfe" + struct.pack("<I", n)
    else:
        return b"\xff" + struct.pack("<Q", n)


def serialize_unsigned_tx(inputs, outputs, locktime=0, version=2):
    """
    Build a raw unsigned transaction (no witness).
    This is what goes into the PSBT global map as the unsigned tx.

    inputs: list of {txid, vout, sequence}
    outputs: list of {value_sats, script_pubkey_hex}
    """
    buf = b""
    buf += struct.pack("<I", version)
    buf += varint(len(inputs))

    for inp in inputs:
        # txid needs to be reversed (internal byte order)
        txid_bytes = bytes.fromhex(inp["txid"])[::-1]
        buf += txid_bytes
        buf += struct.pack("<I", inp["vout"])
        buf += varint(0)  # empty scriptSig for unsigned
        buf += struct.pack("<I", inp["sequence"])

    buf += varint(len(outputs))

    for out in outputs:
        buf += struct.pack("<Q", out["value_sats"])
        spk = bytes.fromhex(out["script_pubkey_hex"])
        buf += varint(len(spk))
        buf += spk

    buf += struct.pack("<I", locktime)
    return buf
