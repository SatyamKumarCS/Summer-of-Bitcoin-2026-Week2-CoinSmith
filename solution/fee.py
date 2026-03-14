import math
from .estimator import estimate_vbytes
from .coin_selection import select_coins_greedy, InsufficientFundsError, MaxInputsExceededError

DUST_THRESHOLD = 546


def _build_output_list(payments, change_template=None, change_val=0):
    """Put together the output list. Optionally append a change output."""
    outs = []
    for i, p in enumerate(payments):
        outs.append({
            "n": i,
            "value_sats": p["value_sats"],
            "script_pubkey_hex": p["script_pubkey_hex"],
            "script_type": p["script_type"],
            "address": p.get("address", ""),
            "is_change": False,
        })
    if change_template and change_val > 0:
        idx = len(outs)
        outs.append({
            "n": idx,
            "value_sats": change_val,
            "script_pubkey_hex": change_template["script_pubkey_hex"],
            "script_type": change_template["script_type"],
            "address": change_template.get("address", ""),
            "is_change": True,
        })
    return outs


def compute_fee_and_change(selected_inputs, payments, change_template, fee_rate):
    """
    Given a set of already-selected inputs, figure out the fee and
    whether we can afford a change output or need to go send-all.
    
    The tricky part: adding a change output makes the tx bigger which
    raises the fee which might push change below dust. So we try both
    with-change and without-change and pick whichever works.
    """
    in_total = sum(u["value_sats"] for u in selected_inputs)
    pay_total = sum(p["value_sats"] for p in payments)

    in_types = [u["script_type"] for u in selected_inputs]
    pay_out_types = [p["script_type"] for p in payments]

    # -- attempt 1: with change output --
    out_types_chg = pay_out_types + [change_template["script_type"]]
    vb_chg = estimate_vbytes(in_types, out_types_chg)
    fee_chg = math.ceil(fee_rate * vb_chg)
    leftover = in_total - pay_total - fee_chg

    if leftover >= DUST_THRESHOLD:
        outs = _build_output_list(payments, change_template, leftover)
        return {
            "selected_inputs": selected_inputs,
            "outputs": outs,
            "change_output": outs[-1],
            "fee_sats": fee_chg,
            "vbytes": vb_chg,
            "change_index": len(outs) - 1,
        }

    # -- attempt 2: no change (send-all) --
    vb_no = estimate_vbytes(in_types, pay_out_types)
    min_fee = math.ceil(fee_rate * vb_no)
    spare = in_total - pay_total

    if spare < min_fee:
        raise InsufficientFundsError(
            f"Not enough: inputs={in_total}, payments={pay_total}, min fee={min_fee}"
        )

    # everything left over becomes fee
    outs = _build_output_list(payments)
    return {
        "selected_inputs": selected_inputs,
        "outputs": outs,
        "change_output": None,
        "fee_sats": spare,  # all leftover is fee
        "vbytes": vb_no,
        "change_index": None,
    }


def select_and_compute(utxos, payments, change_template, fee_rate, max_inputs=None):
    """
    Full pipeline: pick coins then figure out fee/change.
    
    We start with a rough fee estimate, select coins, then refine.
    If the first attempt doesn't work out we retry with a bigger target.
    """
    pay_total = sum(p["value_sats"] for p in payments)
    pay_types = [p["script_type"] for p in payments]

    # rough first estimate with 1 input
    rough_vb = estimate_vbytes(["p2wpkh"], pay_types)
    rough_fee = math.ceil(fee_rate * rough_vb)
    target = pay_total + rough_fee

    for attempt in range(10):
        try:
            picked = select_coins_greedy(utxos, target, max_inputs)
        except (InsufficientFundsError, MaxInputsExceededError):
            # last resort: grab as many as we can and hope send-all works
            by_val = sorted(utxos, key=lambda u: u["value_sats"], reverse=True)
            limit = max_inputs if max_inputs else len(by_val)
            picked = by_val[:limit]

            if not picked or sum(u["value_sats"] for u in picked) < pay_total:
                raise InsufficientFundsError(
                    f"Can't cover {pay_total} sats with available UTXOs"
                )
            try:
                return compute_fee_and_change(picked, payments, change_template, fee_rate)
            except InsufficientFundsError:
                raise

        try:
            return compute_fee_and_change(picked, payments, change_template, fee_rate)
        except InsufficientFundsError:
            # bump the target and try again
            in_types = [u["script_type"] for u in picked]
            out_types = pay_types + [change_template["script_type"]]
            better_vb = estimate_vbytes(in_types, out_types)
            target = pay_total + math.ceil(fee_rate * better_vb) + (attempt + 1) * 1000

    raise InsufficientFundsError("Couldn't converge on a valid selection after 10 tries")
