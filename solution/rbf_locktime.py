# nSequence / nLockTime logic following the spec's interaction matrix.
#
# Quick reference:
#   rbf=false, no locktime          -> seq=0xFFFFFFFF, lt=0
#   rbf=false, locktime set         -> seq=0xFFFFFFFE, lt=locktime
#   rbf=true, no locktime, no ht    -> seq=0xFFFFFFFD, lt=0
#   rbf=true, no locktime, ht set   -> seq=0xFFFFFFFD, lt=current_height (anti-fee-snipe)
#   rbf=true, locktime set          -> seq=0xFFFFFFFD, lt=locktime

SEQ_FINAL    = 0xFFFFFFFF
SEQ_NO_RBF   = 0xFFFFFFFE   # enables locktime but doesn't signal rbf
SEQ_RBF      = 0xFFFFFFFD


def compute_rbf_locktime(rbf=False, locktime=None, current_height=None):
    if rbf:
        seq = SEQ_RBF
        if locktime is not None:
            lt = locktime
        elif current_height is not None:
            lt = current_height  # anti-fee-sniping
        else:
            lt = 0
    else:
        if locktime is not None:
            seq = SEQ_NO_RBF
            lt = locktime
        else:
            seq = SEQ_FINAL
            lt = 0

    # figure out the type string for the report
    if lt == 0:
        lt_type = "none"
    elif lt < 500_000_000:
        lt_type = "block_height"
    else:
        lt_type = "unix_timestamp"

    return {
        "nsequence": seq,
        "nlocktime": lt,
        "rbf_signaling": seq <= SEQ_RBF,
        "locktime_type": lt_type,
    }
