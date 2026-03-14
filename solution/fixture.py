import json
import re


class FixtureError(Exception):
    """Thrown when something's wrong with the input fixture."""
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


KNOWN_SCRIPT_TYPES = {"p2pkh", "p2wpkh", "p2sh-p2wpkh", "p2tr", "p2wsh"}
KNOWN_NETWORKS = {"mainnet", "testnet", "regtest", "signet"}
HEX_RE = re.compile(r'^[0-9a-fA-F]+$')


def _check_hex(val, name):
    if not isinstance(val, str) or not HEX_RE.match(val) or len(val) % 2:
        raise FixtureError("INVALID_FIXTURE", f"Bad hex for {name}: {val!r}")


def _check_utxo(u, i):
    tag = f"utxos[{i}]"
    if not isinstance(u, dict):
        raise FixtureError("INVALID_FIXTURE", f"{tag} isn't an object")
    for k in ("txid", "vout", "value_sats", "script_pubkey_hex", "script_type"):
        if k not in u:
            raise FixtureError("INVALID_FIXTURE", f"{tag} missing '{k}'")

    _check_hex(u["txid"], f"{tag}.txid")
    if len(u["txid"]) != 64:
        raise FixtureError("INVALID_FIXTURE", f"{tag}.txid should be 64 hex chars")
    if not isinstance(u["vout"], int) or u["vout"] < 0:
        raise FixtureError("INVALID_FIXTURE", f"{tag}.vout must be >= 0")
    if not isinstance(u["value_sats"], int) or u["value_sats"] <= 0:
        raise FixtureError("INVALID_FIXTURE", f"{tag}.value_sats must be positive")
    _check_hex(u["script_pubkey_hex"], f"{tag}.script_pubkey_hex")
    if u["script_type"] not in KNOWN_SCRIPT_TYPES:
        raise FixtureError("INVALID_FIXTURE", f"{tag}.script_type unknown: {u['script_type']}")


def _check_payment(p, i):
    tag = f"payments[{i}]"
    if not isinstance(p, dict):
        raise FixtureError("INVALID_FIXTURE", f"{tag} isn't an object")
    for k in ("script_pubkey_hex", "script_type", "value_sats"):
        if k not in p:
            raise FixtureError("INVALID_FIXTURE", f"{tag} missing '{k}'")
    _check_hex(p["script_pubkey_hex"], f"{tag}.script_pubkey_hex")
    if p["script_type"] not in KNOWN_SCRIPT_TYPES:
        raise FixtureError("INVALID_FIXTURE", f"unknown script type in {tag}")
    if not isinstance(p["value_sats"], int) or p["value_sats"] <= 0:
        raise FixtureError("INVALID_FIXTURE", f"{tag}.value_sats must be positive")


def _check_change(c):
    if not isinstance(c, dict):
        raise FixtureError("INVALID_FIXTURE", "change should be an object")
    for k in ("script_pubkey_hex", "script_type"):
        if k not in c:
            raise FixtureError("INVALID_FIXTURE", f"change missing '{k}'")
    _check_hex(c["script_pubkey_hex"], "change.script_pubkey_hex")
    if c["script_type"] not in KNOWN_SCRIPT_TYPES:
        raise FixtureError("INVALID_FIXTURE", f"bad change script type: {c['script_type']}")


def parse_fixture(path):
    """
    Read and validate a fixture JSON file.
    Returns a cleaned-up dict with all the fields we care about.
    """
    try:
        with open(path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise FixtureError("INVALID_FIXTURE", f"Bad JSON: {e}")
    except FileNotFoundError:
        raise FixtureError("FILE_NOT_FOUND", f"No such file: {path}")
    except Exception as e:
        raise FixtureError("INVALID_FIXTURE", f"Can't read fixture: {e}")

    if not isinstance(data, dict):
        raise FixtureError("INVALID_FIXTURE", "Top-level must be a JSON object")

    # network (optional, defaults to mainnet)
    net = data.get("network")
    if net and net not in KNOWN_NETWORKS:
        raise FixtureError("INVALID_FIXTURE", f"Unknown network: {net}")

    # utxos
    utxos = data.get("utxos")
    if not isinstance(utxos, list) or not utxos:
        raise FixtureError("INVALID_FIXTURE", "Need at least one UTXO")
    for i, u in enumerate(utxos):
        _check_utxo(u, i)

    # payments
    payments = data.get("payments")
    if not isinstance(payments, list) or not payments:
        raise FixtureError("INVALID_FIXTURE", "Need at least one payment")
    for i, p in enumerate(payments):
        _check_payment(p, i)

    # change template
    change = data.get("change")
    if change is None:
        raise FixtureError("INVALID_FIXTURE", "Missing 'change' field")
    _check_change(change)

    # fee rate
    fr = data.get("fee_rate_sat_vb")
    if fr is None:
        raise FixtureError("INVALID_FIXTURE", "Missing fee_rate_sat_vb")
    if not isinstance(fr, (int, float)) or fr <= 0:
        raise FixtureError("INVALID_FIXTURE", "fee_rate_sat_vb must be > 0")

    # optional stuff
    rbf = data.get("rbf", False)
    if not isinstance(rbf, bool):
        raise FixtureError("INVALID_FIXTURE", "rbf should be true or false")

    lt = data.get("locktime")
    if lt is not None and (not isinstance(lt, int) or lt < 0):
        raise FixtureError("INVALID_FIXTURE", "locktime must be a non-negative int")

    ch = data.get("current_height")
    if ch is not None and (not isinstance(ch, int) or ch < 0):
        raise FixtureError("INVALID_FIXTURE", "current_height must be a non-negative int")

    policy = data.get("policy", {})
    mi = policy.get("max_inputs") if isinstance(policy, dict) else None

    return {
        "network": net or "mainnet",
        "utxos": utxos,
        "payments": payments,
        "change": change,
        "fee_rate_sat_vb": fr,
        "rbf": rbf,
        "locktime": lt,
        "current_height": ch,
        "max_inputs": mi,
    }
