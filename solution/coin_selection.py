class InsufficientFundsError(Exception):
    pass


class MaxInputsExceededError(Exception):
    pass


def select_coins_greedy(utxos, target_sats, max_inputs=None):
    """
    Pick UTXOs largest-first until we hit the target.
    Simple but works well enough for most cases.
    """
    by_value = sorted(utxos, key=lambda u: u["value_sats"], reverse=True)

    picked = []
    running_total = 0

    for utxo in by_value:
        if max_inputs and len(picked) >= max_inputs:
            break
        picked.append(utxo)
        running_total += utxo["value_sats"]
        if running_total >= target_sats:
            break

    if running_total < target_sats:
        if max_inputs and len(picked) >= max_inputs:
            raise MaxInputsExceededError(
                f"Can't fund {target_sats} sats within {max_inputs} inputs "
                f"(best effort: {len(picked)} inputs, {running_total} sats)"
            )
        raise InsufficientFundsError(
            f"Need {target_sats} sats but only have {running_total} across {len(utxos)} UTXOs"
        )

    return picked
