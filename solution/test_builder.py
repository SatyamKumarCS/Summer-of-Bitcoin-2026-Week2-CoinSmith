"""
Unit tests for the PSBT transaction builder.
Run with: python3 -m unittest tests.test_builder -v
"""

import sys, os, json, math, base64, struct, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.estimator import estimate_vbytes, estimate_weight
from src.coin_selection import select_coins_greedy, InsufficientFundsError, MaxInputsExceededError
from src.fee import compute_fee_and_change, select_and_compute, DUST_THRESHOLD
from src.rbf_locktime import compute_rbf_locktime
from src.psbt import build_psbt, PSBT_MAGIC
from src.transaction import serialize_unsigned_tx, varint
from src.report import generate_warnings, build_report, build_error_report
from src.fixture import parse_fixture, FixtureError


# ----- helpers -----

def _utxo(prefix, vout=0, sats=100000, stype="p2wpkh"):
    spk = {
        "p2wpkh": "0014" + "aa" * 20,
        "p2tr": "5120" + "bb" * 32,
        "p2pkh": "76a914" + "cc" * 20 + "88ac",
        "p2sh-p2wpkh": "a914" + "dd" * 20 + "87",
    }
    # make sure the txid is valid hex (pad with 'a' not '0' to avoid prefix issues)
    hex_prefix = prefix.encode().hex()
    txid = hex_prefix.ljust(64, "0")[:64]
    return {
        "txid": txid,
        "vout": vout, "value_sats": sats,
        "script_pubkey_hex": spk.get(stype, spk["p2wpkh"]),
        "script_type": stype, "address": "bc1qtest",
    }

def _payment(sats=70000, stype="p2wpkh"):
    spk = {"p2wpkh": "0014" + "11" * 20, "p2tr": "5120" + "22" * 32}
    return {
        "address": "bc1qpay", "value_sats": sats,
        "script_pubkey_hex": spk.get(stype, spk["p2wpkh"]),
        "script_type": stype,
    }

def _change(stype="p2wpkh"):
    spk = {"p2wpkh": "0014" + "ff" * 20, "p2tr": "5120" + "ee" * 32}
    return {
        "address": "bc1qchg",
        "script_pubkey_hex": spk.get(stype, spk["p2wpkh"]),
        "script_type": stype,
    }


# ===== vbytes estimation =====

class TestVbytes(unittest.TestCase):

    def test_single_p2wpkh(self):
        # 1-in-1-out: overhead(42) + in(271) + out(124) = 437 WU => 110 vB
        self.assertEqual(estimate_vbytes(["p2wpkh"], ["p2wpkh"]), 110)

    def test_one_in_two_out(self):
        # with change: 42 + 271 + 124*2 = 561 => 141
        self.assertEqual(estimate_vbytes(["p2wpkh"], ["p2wpkh", "p2wpkh"]), 141)

    def test_mixed_inputs(self):
        self.assertEqual(estimate_vbytes(["p2wpkh", "p2tr"], ["p2wpkh"]), 167)

    def test_legacy_no_witness(self):
        # p2pkh only => no witness overhead => 40 + 592 + 136 = 768 => 192
        self.assertEqual(estimate_vbytes(["p2pkh"], ["p2pkh"]), 192)


# ===== coin selection =====

class TestSelection(unittest.TestCase):

    def test_picks_largest(self):
        us = [_utxo("a", sats=10000), _utxo("b", sats=50000), _utxo("c", sats=30000)]
        got = select_coins_greedy(us, 40000)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["value_sats"], 50000)

    def test_picks_multiple(self):
        us = [_utxo("a", sats=20000), _utxo("b", sats=30000), _utxo("c", sats=25000)]
        got = select_coins_greedy(us, 50000)
        self.assertEqual(len(got), 2)
        self.assertGreaterEqual(sum(u["value_sats"] for u in got), 50000)

    def test_insufficient(self):
        with self.assertRaises(InsufficientFundsError):
            select_coins_greedy([_utxo("x", sats=500)], 99999)

    def test_max_inputs(self):
        us = [_utxo(f"u{i}", sats=5000) for i in range(10)]
        with self.assertRaises((InsufficientFundsError, MaxInputsExceededError)):
            select_coins_greedy(us, 40000, max_inputs=3)


# ===== fee / change =====

class TestFeeLogic(unittest.TestCase):

    def test_creates_change(self):
        r = compute_fee_and_change([_utxo("a", sats=100000)], [_payment(70000)], _change(), 5)
        self.assertIsNotNone(r["change_index"])
        self.assertGreaterEqual(r["outputs"][r["change_index"]]["value_sats"], DUST_THRESHOLD)

    def test_send_all(self):
        r = compute_fee_and_change([_utxo("a", sats=10000)], [_payment(9000)], _change(), 5)
        self.assertIsNone(r["change_index"])
        out_total = sum(o["value_sats"] for o in r["outputs"])
        self.assertEqual(r["fee_sats"], 10000 - out_total)

    def test_balance_holds(self):
        r = compute_fee_and_change([_utxo("a", sats=200000)], [_payment(150000)], _change(), 5)
        ins = 200000
        outs = sum(o["value_sats"] for o in r["outputs"])
        self.assertEqual(ins, outs + r["fee_sats"])

    def test_fee_target(self):
        r = compute_fee_and_change([_utxo("a", sats=100000)], [_payment(50000)], _change(), 10)
        self.assertGreaterEqual(r["fee_sats"], math.ceil(10 * r["vbytes"]))


# ===== rbf / locktime =====

class TestRBF(unittest.TestCase):

    def test_defaults(self):
        r = compute_rbf_locktime()
        self.assertEqual(r["nsequence"], 0xFFFFFFFF)
        self.assertEqual(r["nlocktime"], 0)
        self.assertFalse(r["rbf_signaling"])
        self.assertEqual(r["locktime_type"], "none")

    def test_rbf_only(self):
        r = compute_rbf_locktime(rbf=True)
        self.assertEqual(r["nsequence"], 0xFFFFFFFD)
        self.assertTrue(r["rbf_signaling"])

    def test_anti_fee_snipe(self):
        r = compute_rbf_locktime(rbf=True, current_height=860000)
        self.assertEqual(r["nlocktime"], 860000)
        self.assertEqual(r["locktime_type"], "block_height")

    def test_explicit_locktime_wins(self):
        r = compute_rbf_locktime(rbf=True, locktime=850000, current_height=860000)
        self.assertEqual(r["nlocktime"], 850000)

    def test_locktime_without_rbf(self):
        r = compute_rbf_locktime(locktime=850000)
        self.assertEqual(r["nsequence"], 0xFFFFFFFE)
        self.assertFalse(r["rbf_signaling"])

    def test_unix_timestamp(self):
        r = compute_rbf_locktime(locktime=1700000000)
        self.assertEqual(r["locktime_type"], "unix_timestamp")

    def test_boundary_block(self):
        r = compute_rbf_locktime(locktime=499999999)
        self.assertEqual(r["locktime_type"], "block_height")

    def test_boundary_timestamp(self):
        r = compute_rbf_locktime(locktime=500000000)
        self.assertEqual(r["locktime_type"], "unix_timestamp")


# ===== PSBT =====

class TestPSBT(unittest.TestCase):

    def _simple_psbt(self):
        ins = [{"txid": "aa" * 32, "vout": 0, "sequence": 0xFFFFFFFF,
                "value_sats": 100000, "script_pubkey_hex": "0014" + "11" * 20,
                "script_type": "p2wpkh"}]
        outs = [{"value_sats": 90000, "script_pubkey_hex": "0014" + "22" * 20}]
        return build_psbt(ins, outs)

    def test_magic(self):
        raw = base64.b64decode(self._simple_psbt())
        self.assertEqual(raw[:5], PSBT_MAGIC)

    def test_valid_b64(self):
        raw = base64.b64decode(self._simple_psbt())
        self.assertGreater(len(raw), 10)


# ===== transaction serialization =====

class TestTxSerialization(unittest.TestCase):

    def test_varint_small(self):
        self.assertEqual(varint(0), b"\x00")
        self.assertEqual(varint(252), b"\xfc")

    def test_varint_medium(self):
        v = varint(253)
        self.assertEqual(v[0:1], b"\xfd")
        self.assertEqual(len(v), 3)

    def test_version_and_locktime(self):
        raw = serialize_unsigned_tx(
            [{"txid": "aa" * 32, "vout": 0, "sequence": 0xFFFFFFFF}],
            [{"value_sats": 50000, "script_pubkey_hex": "0014" + "11" * 20}],
        )
        self.assertEqual(struct.unpack("<I", raw[:4])[0], 2)   # version
        self.assertEqual(struct.unpack("<I", raw[-4:])[0], 0)   # locktime


# ===== warnings =====

class TestWarnings(unittest.TestCase):

    def test_send_all(self):
        codes = [w["code"] for w in generate_warnings(1000, 5.0, None, False)]
        self.assertIn("SEND_ALL", codes)

    def test_rbf(self):
        codes = [w["code"] for w in generate_warnings(500, 5.0, {"value_sats": 9999}, True)]
        self.assertIn("RBF_SIGNALING", codes)

    def test_high_fee_amount(self):
        codes = [w["code"] for w in generate_warnings(2_000_000, 5.0, {"value_sats": 9999}, False)]
        self.assertIn("HIGH_FEE", codes)

    def test_high_fee_rate(self):
        codes = [w["code"] for w in generate_warnings(500, 250.0, {"value_sats": 9999}, False)]
        self.assertIn("HIGH_FEE", codes)

    def test_clean_tx(self):
        self.assertEqual(generate_warnings(500, 5.0, {"value_sats": 9999}, False), [])


# ===== fixture parsing =====

class TestFixtureParsing(unittest.TestCase):

    def _write_json(self, obj):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(obj, f)
        f.close()
        return f.name

    def test_valid(self):
        p = self._write_json({
            "network": "mainnet", "utxos": [_utxo("z")],
            "payments": [_payment()], "change": _change(), "fee_rate_sat_vb": 5,
        })
        r = parse_fixture(p)
        os.unlink(p)
        self.assertEqual(r["network"], "mainnet")

    def test_no_utxos(self):
        p = self._write_json({
            "network": "mainnet", "payments": [_payment()],
            "change": _change(), "fee_rate_sat_vb": 5,
        })
        with self.assertRaises(FixtureError):
            parse_fixture(p)
        os.unlink(p)

    def test_bad_json(self):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        f.write("{nope")
        f.close()
        with self.assertRaises(FixtureError):
            parse_fixture(f.name)
        os.unlink(f.name)


# ===== error report =====

class TestErrorReport(unittest.TestCase):
    def test_structure(self):
        r = build_error_report("OOPS", "something broke")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"]["code"], "OOPS")


# ===== end-to-end =====

class TestEndToEnd(unittest.TestCase):
    def test_basic(self):
        r = select_and_compute([_utxo("z", sats=100000)], [_payment(70000)], _change(), 5)
        ins = sum(i["value_sats"] for i in r["selected_inputs"])
        outs = sum(o["value_sats"] for o in r["outputs"])
        self.assertEqual(ins, outs + r["fee_sats"])


if __name__ == "__main__":
    unittest.main()
