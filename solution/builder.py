#!/usr/bin/env python3
"""
Main CLI entry point for the PSBT builder.
Usage: python3 builder.py <fixture.json> <output.json>
"""
import sys
import json

from src.fixture import parse_fixture, FixtureError
from src.coin_selection import InsufficientFundsError, MaxInputsExceededError
from src.fee import select_and_compute
from src.rbf_locktime import compute_rbf_locktime
from src.psbt import build_psbt
from src.report import build_report, build_error_report


def build_transaction(fixture_path):
    """Run the full build pipeline on a fixture file."""
    fixture = parse_fixture(fixture_path)

    # figure out rbf/locktime settings
    rl = compute_rbf_locktime(
        rbf=fixture["rbf"],
        locktime=fixture["locktime"],
        current_height=fixture["current_height"],
    )

    # coin selection + fee/change calculation
    result = select_and_compute(
        utxos=fixture["utxos"],
        payments=fixture["payments"],
        change_template=fixture["change"],
        fee_rate=fixture["fee_rate_sat_vb"],
        max_inputs=fixture["max_inputs"],
    )

    # build the actual PSBT
    psbt_ins = []
    for inp in result["selected_inputs"]:
        psbt_ins.append({
            "txid": inp["txid"],
            "vout": inp["vout"],
            "sequence": rl["nsequence"],
            "value_sats": inp["value_sats"],
            "script_pubkey_hex": inp["script_pubkey_hex"],
            "script_type": inp["script_type"],
        })

    psbt_outs = [
        {"value_sats": o["value_sats"], "script_pubkey_hex": o["script_pubkey_hex"]}
        for o in result["outputs"]
    ]

    psbt_b64 = build_psbt(psbt_ins, psbt_outs, locktime=rl["nlocktime"])

    # format inputs for the report
    report_ins = [{
        "txid": inp["txid"],
        "vout": inp["vout"],
        "value_sats": inp["value_sats"],
        "script_pubkey_hex": inp["script_pubkey_hex"],
        "script_type": inp["script_type"],
        "address": inp.get("address", ""),
    } for inp in result["selected_inputs"]]

    return build_report(
        network=fixture["network"],
        strategy="greedy",
        selected_inputs=report_ins,
        outputs=result["outputs"],
        change_index=result["change_index"],
        fee_sats=result["fee_sats"],
        vbytes=result["vbytes"],
        rbf_signaling=rl["rbf_signaling"],
        locktime=rl["nlocktime"],
        locktime_type=rl["locktime_type"],
        psbt_base64=psbt_b64,
        fee_rate_sat_vb=fixture["fee_rate_sat_vb"],
    )


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 builder.py <fixture.json> <output.json>", file=sys.stderr)
        sys.exit(1)

    fixture_path = sys.argv[1]
    output_path = sys.argv[2]

    try:
        report = build_transaction(fixture_path)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

    except FixtureError as e:
        with open(output_path, "w") as f:
            json.dump(build_error_report(e.code, e.message), f, indent=2)
        print(f"Error: {e.message}", file=sys.stderr)
        sys.exit(1)

    except (InsufficientFundsError, MaxInputsExceededError) as e:
        with open(output_path, "w") as f:
            json.dump(build_error_report("INSUFFICIENT_FUNDS", str(e)), f, indent=2)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    except Exception as e:
        with open(output_path, "w") as f:
            json.dump(build_error_report("INTERNAL_ERROR", str(e)), f, indent=2)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
