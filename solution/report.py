DUST_THRESHOLD = 546


def generate_warnings(fee_sats, fee_rate, change_output, rbf_signaling):
    """Figure out which warnings apply to this transaction."""
    w = []

    if fee_sats > 1_000_000 or fee_rate > 200:
        w.append({"code": "HIGH_FEE"})

    if change_output and change_output["value_sats"] < DUST_THRESHOLD:
        w.append({"code": "DUST_CHANGE"})

    if change_output is None:
        w.append({"code": "SEND_ALL"})

    if rbf_signaling:
        w.append({"code": "RBF_SIGNALING"})

    return w


def build_report(network, strategy, selected_inputs, outputs, change_index,
                 fee_sats, vbytes, rbf_signaling, locktime, locktime_type,
                 psbt_base64, fee_rate_sat_vb):
    """Assemble the full JSON report."""
    actual_rate = fee_sats / vbytes if vbytes else 0.0

    chg_out = outputs[change_index] if change_index is not None else None
    warnings = generate_warnings(fee_sats, actual_rate, chg_out, rbf_signaling)

    return {
        "ok": True,
        "network": network,
        "strategy": strategy,
        "selected_inputs": selected_inputs,
        "outputs": outputs,
        "change_index": change_index,
        "fee_sats": fee_sats,
        "fee_rate_sat_vb": round(actual_rate, 2),
        "vbytes": vbytes,
        "rbf_signaling": rbf_signaling,
        "locktime": locktime,
        "locktime_type": locktime_type,
        "psbt_base64": psbt_base64,
        "warnings": warnings,
    }


def build_error_report(code, message):
    return {
        "ok": False,
        "error": {"code": code, "message": message},
    }
