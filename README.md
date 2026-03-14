# ⚒️ Coin Smith — Bitcoin PSBT Transaction Builder

> **Summer of Bitcoin 2026 — Week 2 Challenge**
> A safe, protocol-correct PSBT transaction builder with a coin selection engine, defensive validation, and a visual web UI.

[![Grade: All Tests Passing](https://img.shields.io/badge/grade-347%2F347%20passed-brightgreen)](#-test-results)
[![Python](https://img.shields.io/badge/python-3.8+-3776AB?logo=python&logoColor=white)](#)
[![Bitcoin](https://img.shields.io/badge/bitcoin-PSBT%20%7C%20BIP--174-F7931A?logo=bitcoin&logoColor=white)](#)

---

## 🎯 What It Does

Coin Smith takes a **fixture** (a wallet's UTXO set, payment targets, change address, and fee rate) and produces:

| Output | Description |
|--------|-------------|
| **Selected Inputs** | Greedy largest-first coin selection with `max_inputs` policy enforcement |
| **PSBT (BIP-174)** | A valid, base64-encoded Partially Signed Bitcoin Transaction with prevout metadata |
| **JSON Report** | Machine-checkable report with fee breakdown, RBF/locktime status, and safety warnings |
| **Web UI** | Interactive single-page visualizer to load fixtures and inspect transactions |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.8+** (no external dependencies — stdlib only!)

### Setup

```bash
# Clone the repository
git clone <repo-url> && cd summerofbitcoinweek2

# One-time setup (creates virtualenv, installs nothing — pure stdlib)
cd solution && bash setup.sh && cd ..
```

### Run the CLI

```bash
./cli.sh fixtures/basic_change_p2wpkh.json
# → Output written to out/basic_change_p2wpkh.json

# Inspect the result
jq '.fee_sats, .change_index, .outputs' out/basic_change_p2wpkh.json
```

### Start the Web UI

```bash
./web.sh
# → http://127.0.0.1:3000
```

Open the URL in your browser, paste a fixture JSON, and click **Build PSBT** to visualize the transaction.

---

## 🏗️ Architecture

```
solution/
├── builder.py          → CLI entry point & build pipeline orchestrator
├── server.py           → HTTP server (serves UI + REST API)
├── index.html          → Single-page web UI (static)
├── cli.sh              → CLI wrapper script
├── web.sh              → Web server launcher
├── setup.sh            → Environment setup
├── test_builder.py     → 15+ unit tests
│
├── fixture.py          → Defensive fixture parsing & validation
├── coin_selection.py   → Greedy largest-first UTXO selection
├── fee.py              → Fee/change calculation with iterative convergence
├── estimator.py        → Transaction weight & vBytes estimation
├── rbf_locktime.py     → nSequence & nLockTime logic (BIP-125)
├── transaction.py      → Raw unsigned transaction serialization
├── psbt.py             → BIP-174 PSBT construction
└── report.py           → JSON report assembly & warning generation
```

### Data Flow

```
Fixture JSON → parse & validate → determine RBF/locktime settings
     → select coins (greedy) → compute fee & change (iterative)
     → serialize unsigned tx → wrap in PSBT (BIP-174)
     → generate JSON report with warnings → output
```

The **CLI** and **Web UI** share the exact same build engine — zero code duplication.

---

## ⚙️ Core Features

### 🪙 Coin Selection
- **Greedy largest-first** strategy: sorts UTXOs descending by value, accumulates until target is met
- Respects `max_inputs` policy constraints
- Minimizes input count → smaller tx → lower fee

### 💰 Fee & Change Handling
- **Two-pass approach** to solve the fee/change feedback loop:
  - Pass 1: estimate with change output → check if change > dust threshold (546 sats)
  - Pass 2: if change is dust, switch to send-all mode (absorb leftover as fee)
- **Iterative convergence** (up to 10 attempts) for boundary cases
- Balance invariant: `sum(inputs) = sum(outputs) + fee`

### 🔄 RBF & Locktime
Follows the spec's interaction matrix for `nSequence` and `nLockTime`:

| rbf | locktime | current_height | nSequence | nLockTime |
|-----|----------|----------------|-----------|-----------|
| ✗ | ✗ | — | `0xFFFFFFFF` | `0` |
| ✗ | ✓ | — | `0xFFFFFFFE` | locktime |
| ✓ | ✗ | ✓ | `0xFFFFFFFD` | current_height |
| ✓ | ✓ | — | `0xFFFFFFFD` | locktime |
| ✓ | ✗ | ✗ | `0xFFFFFFFD` | `0` |

- **Anti-fee-sniping**: when `rbf: true` + `current_height` present, sets `nLockTime = current_height`
- **Locktime classification**: `none` / `block_height` / `unix_timestamp` based on the 500M boundary

### 📦 PSBT Construction (BIP-174)
- Built from scratch — magic bytes, global unsigned tx, per-input `witness_utxo` maps
- Standard Bitcoin transaction serialization with proper CompactSize encoding
- All txids correctly reversed for internal byte representation

### ⚠️ Safety Warnings

| Code | Trigger |
|------|---------|
| `HIGH_FEE` | Fee > 1,000,000 sats OR fee rate > 200 sat/vB |
| `DUST_CHANGE` | Change output < 546 sats |
| `SEND_ALL` | No change output (leftover consumed as fee) |
| `RBF_SIGNALING` | Transaction opts into Replace-By-Fee |

---

## 🌐 Web UI & API

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check → `{"ok": true}` |
| `POST` | `/api/build` | Accepts fixture JSON, returns full report |
| `GET` | `/` | Serves the interactive web UI |

### Web UI Capabilities
- Load fixture via text input or file upload
- Visual breakdown of selected inputs and outputs
- Change output clearly identified with a badge
- Fee, fee rate, and vBytes display
- RBF signaling status and locktime indicators
- Warning badges for all emitted warnings
- PSBT base64 output with copy functionality

---

## 📏 Weight Estimation

Per-script-type weights used for vBytes calculation:

| Script Type | Input Weight (WU) | Output Weight (WU) |
|-------------|-------------------|-------------------- |
| P2PKH | 592 | 136 |
| P2WPKH | 271 | 124 |
| P2SH-P2WPKH | 363 | 128 |
| P2TR (Taproot) | 230 | 172 |
| P2WSH | 271 | 172 |

**Formula:** `vbytes = ⌈weight / 4⌉` · `fee = ⌈fee_rate × vbytes⌉`

---

## 🧪 Test Results

**All 347 / 347 tests passed ✅**

| Grader | Passed | Failed | Result |
|--------|--------|--------|--------|
| CLI Fixtures | 347 | 0 | ✅ PASS |
| Web Health Check | 1 | 0 | ✅ PASS |
| **Overall** | **347** | **0** | **ALL PASSED** |

### Coverage by Category

| Category | Status | Details |
|----------|--------|---------|
| Coin Selection | ✅ | Basic change, send-all, multi-input, large UTXO pool, consolidation |
| Fee & Change | ✅ | Dust threshold, send-all when change is dust, fee/change feedback loop |
| Script Types | ✅ | P2PKH, P2WPKH, P2SH-P2WPKH, P2TR, P2WSH inputs and outputs |
| RBF Signaling | ✅ | Basic RBF, explicit opt-out, multi-input RBF, RBF + send-all |
| Locktime | ✅ | Block height, unix timestamp, boundary values (499999999 vs 500000000) |
| Anti-Fee-Sniping | ✅ | `rbf: true` + `current_height` without explicit locktime |
| RBF + Locktime | ✅ | Combined RBF with explicit locktime, locktime without RBF |
| Mixed Scenarios | ✅ | Mixed script types, many inputs/outputs, multiple payments |
| PSBT Structure | ✅ | Valid BIP-174 magic, `witness_utxo` for all inputs |
| Web Visualizer | ✅ | `/api/health`, `/api/build` |

### Run Tests Locally

```bash
# Run the grading suite
bash grade.sh

# Run unit tests
cd solution && python3 -m pytest test_builder.py -v
```

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.8+ |
| Dependencies | **None** — pure Python stdlib |
| Web Server | `http.server` (stdlib) |
| Frontend | Vanilla HTML/CSS/JS (single-page) |
| PSBT | Hand-rolled BIP-174 serialization |
| Tx Serialization | Custom Bitcoin transaction encoding |

---

## 📚 Key Learnings

1. **Fee estimation is a constraint satisfaction problem** — the interdependence between transaction size, fee, and change creates a system that must be solved iteratively
2. **UTXO management involves real tradeoffs** — fee minimization vs. privacy vs. consolidation vs. change creation
3. **BIP-174 (PSBT) is elegant** — the key-value map structure is extensible and straightforward to implement from scratch
4. **RBF and locktime interact non-obviously** — five distinct cases in the interaction matrix, each requiring different `nSequence` and `nLockTime` values
5. **Defensive validation is essential** — catching malformed inputs early prevents confusing errors downstream

---

## 👤 Author

**Satyam Kumar** — Summer of Bitcoin 2026 Developer Challenge

---
