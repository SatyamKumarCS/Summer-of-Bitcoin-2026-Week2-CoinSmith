import math

# Input weight (in weight units) for each script type.
# These come from measuring typical input sizes on mainnet.
# Non-witness bytes count 4x, witness bytes count 1x.
INPUT_WEIGHT = {
    "p2pkh":       592,   # legacy, no witness at all
    "p2wpkh":      271,   # native segwit v0
    "p2sh-p2wpkh": 363,   # wrapped segwit
    "p2tr":        230,   # taproot (schnorr sig is smaller)
    "p2wsh":       271,
}

# Output weight for each type (just scriptPubKey length * 4 basically)
OUTPUT_WEIGHT = {
    "p2pkh":       136,
    "p2wpkh":      124,
    "p2sh-p2wpkh": 128,
    "p2tr":        172,
    "p2wsh":       172,
}

# base overhead: version(4) + locktime(4) + vin count(~1) + vout count(~1) = 10 bytes * 4 = 40 WU
TX_OVERHEAD_BASE = 40
SEGWIT_MARKER_WEIGHT = 2  # the 0x00 0x01 marker+flag


def _has_witness(input_types):
    segwit = {"p2wpkh", "p2sh-p2wpkh", "p2tr", "p2wsh"}
    for t in input_types:
        if t in segwit:
            return True
    return False


def estimate_weight(input_types, output_types):
    w = TX_OVERHEAD_BASE
    if _has_witness(input_types):
        w += SEGWIT_MARKER_WEIGHT

    for t in input_types:
        w += INPUT_WEIGHT.get(t, INPUT_WEIGHT["p2wpkh"])
    for t in output_types:
        w += OUTPUT_WEIGHT.get(t, OUTPUT_WEIGHT["p2wpkh"])
    return w


def estimate_vbytes(input_types, output_types):
    return math.ceil(estimate_weight(input_types, output_types) / 4)
