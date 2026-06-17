<div align="center">

# ⚡ Institutional HFT Arbitrage Bot

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![Solana](https://img.shields.io/badge/Solana-Mainnet-purple)](https://solana.com)
[![Ethereum](https://img.shields.io/badge/EVM-Sepolia%2FMainnet-blueviolet)](https://ethereum.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Production--Ready-brightgreen)](https://github.com)

**High-Frequency Trading Arbitrage Bot for Solana & EVM chains**  
*MEV-protected · Cross-DEX · Circuit Breaker · Institutional Grade*

</div>

---

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Key Features](#key-features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Core Components](#core-components)
- [Risk Management](#risk-management)
- [Performance](#performance)
- [Pre-Flight Checklist](#pre-flight-checklist)
- [Monitoring](#monitoring)
- [Roadmap](#roadmap)
- [Disclaimer](#disclaimer)

---

## Overview

This is an **institutional-grade High-Frequency Trading (HFT) arbitrage bot** designed to capture cross-DEX and cross-chain opportunities in real-time. It integrates **Solana (Raydium)** and **EVM (Uniswap V2/V3)** with enterprise-level MEV protection, dynamic path finding, and comprehensive risk management.

| Metric | Target |
|--------|--------|
| **End-to-End Latency** | <500ms (detection → simulation → submission) |
| **Chains** | Solana Mainnet, Ethereum/Sepolia |
| **CEX Integration** | Binance (spread monitoring) |
| **MEV Protection** | Flashbots + Jito Bundles |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         HFTOrchestrator                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ EVM Listener │  │ SOL Listener │  │     Mempool Scanner      │  │
│  │  (WebSocket) │  │  (WebSocket) │  │    (Pending TX Stream)   │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬──────────────┘  │
│         │                 │                      │                  │
│         └─────────────────┼──────────────────────┘                  │
│                           ▼                                          │
│              ┌────────────────────────┐                               │
│              │    PriceFeedEngine     │                               │
│              │  (Pyth + Chainlink +   │                               │
│              │   Uniswap V3 TWAP)     │                               │
│              └──────────┬─────────────┘                               │
│                         ▼                                            │
│              ┌────────────────────────┐                               │
│              │    PriceCache (TTL 1s) │                               │
│              └──────────┬─────────────┘                               │
│                         ▼                                            │
│         ┌───────────────────────────────┐                            │
│         │   PathFinder + Quantitative   │                            │
│         │   Engine (Bellman-Ford / BFS) │                            │
│         └───────────────┬───────────────┘                            │
│                         ▼                                            │
│         ┌───────────────────────────────┐                            │
│         │   RiskManager (Circuit Breaker)│                            │
│         └───────────────┬───────────────┘                            │
│                         ▼                                            │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                     EXECUTION LAYER                             │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │  │
│  │  │ EVM Executor│  │ SOL Executor│  │  MEVDispatcher      │  │  │
│  │  │ (Flashbots) │  │ (Jito Bundle)│  │  (Bundle Signing)   │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                     MONITORING LAYER                          │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │  │
│  │  │  Watchdog   │  │  Dashboard  │  │  Health Check API   │  │  │
│  │  │(Gas Bump)   │  │(SQLite +   │  │  (HTTP /metrics)    │  │  │
│  │  │             │  │ Telegram)   │  │                     │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Key Features

### 🔒 MEV Protection
- **Flashbots Bundles** — EIP-191 compliant signing with private relay
- **Jito Bundles** — Dynamic tip optimization based on network floor
- **Fallback Strategy** — Auto-fallback to public mempool if relay fails

### 🧠 Smart Routing
- **Bellman-Ford Algorithm** — Negative cycle detection for arbitrage proof
- **Bounded BFS** — Real-time pathfinding with configurable max hops
- **Optimal Input Calculation** — Mathematical formula for maximal profit extraction

### 🛡️ Risk Management
- **Circuit Breaker** — Auto-shutdown after daily loss limit or consecutive losses
- **Gas Guard** — Abort execution if gas exceeds threshold
- **Transaction Watchdog** — Auto gas bump for stuck transactions

### 📊 Monitoring
- **Health Check API** — `GET /health` and `GET /metrics` (Prometheus-compatible)
- **Telegram Dashboard** — Automated P&L reports every 6 hours
- **SQLite Logging** — Non-blocking trade history with async writes

---

## Installation

```bash
# Clone repository
git clone https://github.com/yourusername/hft-arbitrage-bot.git
cd hft-arbitrage-bot

# Install dependencies
pip install -r requirements.txt

# Or install manually
pip install web3 solders solana structlog aiohttp websockets python-dotenv uvloop
```

### Requirements

```text
python>=3.10
web3>=6.0
solders>=0.18
solana>=0.30
aiohttp>=3.8
websockets>=11.0
structlog>=23.0
python-dotenv>=1.0
uvloop>=0.17
```

---

## Configuration

Create `.env` file in project root:

```bash
# Core
MIN_PROFIT_USD=15.0

# Solana
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
SOLANA_WS_URL=wss://api.mainnet-beta.solana.com
SOLANA_PRIVATE_KEY=your_base58_private_key_here

# EVM
EVM_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
EVM_WS_URL=wss://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
EVM_PRIVATE_KEY=0x_your_64_hex_char_private_key

# Pool Configuration
POOL_B_EVM=0x_address_of_second_uniswap_pool
EXECUTOR_CONTRACT=0x_your_deployed_arbitrage_contract

# MEV Protection
USE_MEV_PROTECTION=true
FLASHBOTS_SIGNING_KEY=0x_your_flashbots_key
FLASHBOTS_RELAY_URL=https://relay.flashbots.net

# Jito
JITO_BUNDLE_URL=https://mainnet.block-engine.jito.wtf/api/v1/bundles
JITO_TIP_MULTIPLIER=1.2

# Risk Management
MAX_DAILY_LOSS_USD=500.0
MAX_GAS_GWEI=200.0
CIRCUIT_BREAKER_COOLDOWN=3600

# Mempool Scanner
SCAN_MEMPOOL=true
DEX_ROUTERS=0x7a250d5630b4cf539739df2c5dacb4c659f2488d

# Cross-Chain (Detection Only)
CROSS_CHAIN_ENABLED=false
BINANCE_API_KEY=your_binance_api_key
BINANCE_SECRET_KEY=your_binance_secret

# Telegram Dashboard
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Monitoring
HEALTH_CHECK_PORT=8080
```

---

## Core Components

### PriceFeedEngine
Multi-source oracle with hierarchical fallback:

```python
class PriceFeedEngine:
    async def get_solana_price(self, pyth_price_id: str) -> float
    async def get_evm_price(self, chainlink_address: str) -> float
    async def _get_twap_fallback(self, pool_address: str) -> float  # Uniswap V3
```

**Why this matters:** HFT requires accurate prices resilient to oracle failure. TWAP fallback prevents the bot from going "blind" when the primary oracle is down.

### PathFinder
Dual-algorithm arbitrage detection:

```python
class PathFinder:
    def find_best_circular_arbitrage(self, start_token, max_hops=3)  # Bounded BFS for speed
    def find_negative_cycle(self, start_token)  # Bellman-Ford for mathematical rigor
```

### QuantitativeEngine
GIL-bypassed optimal amount calculation:

```python
class QuantitativeEngine:
    @staticmethod
    def calculate_optimal_arbitrage(r1_x, r1_y, r2_x, r2_y, fee_bps) -> Tuple[int, int]
```

Formula: `optimal = (√(r1x·r2x·r1y·r2y)·f - r1x·r2y) / (r2y·f)`

### NonceManager
Thread-safe nonce management with pending counter:

```python
class NonceManager:
    async def get_nonce(self) -> int
    async def decrement_nonce()      # Rollback on failure
    async def confirm_nonce()        # Confirm on success
    async def sync_nonce()           # Recovery from desync
```

### MEVDispatcher
Dual-mode transaction submission:

```python
class MEVDispatcher:
    async def send_transaction(self, signed_tx) -> Tuple[str, bool]
    # Returns: (tx_hash, is_private_bundle)
```

### JitoBundleSender
Persistent session for Jito Block Engine:

```python
class JitoBundleSender:
    async def send_bundle(self, tx_base64: str, tip_account: str) -> Tuple[bool, str]
```

### TransactionWatchdog
Auto gas bump for stuck transactions:

```python
class TransactionWatchdog:
    async def _speed_up_transaction(self, nonce, tx_params)
    # Gas bump: 20% increase every 60s
```

### RiskManager
Multi-layer safety system:

```python
class RiskManager:
    def check_gas_price(self, gas_price_gwei) -> bool
    def check_daily_limit(self, profit_usd) -> bool
    def record_trade(self, profit_usd, success)
```

| Risk | Threshold | Action |
|------|-----------|--------|
| Gas Price Spike | >200 gwei | Abort execution |
| Daily Loss | >$500 | Circuit breaker 1 hour |
| Consecutive Loss | 5 trades | Circuit breaker 1 hour |

### HealthCheckServer
Prometheus-compatible monitoring:

```python
class HealthCheckServer:
    async def health_handler(self, request)   # GET /health
    async def metrics_handler(self, request)  # GET /metrics
```

---

## Risk Management

```
┌─────────────────────┬──────────────┬──────────────────────────────┐
│ Risk                │ Threshold    │ Action                       │
├─────────────────────┼──────────────┼──────────────────────────────┤
│ Gas Price Spike     │ >200 gwei    │ Abort execution              │
│ Daily Loss          │ >$500        │ Circuit breaker 1 hour       │
│ Consecutive Loss    │ 5 trades     │ Circuit breaker 1 hour       │
│ Simulation Fail     │ Any          │ Do not submit tx             │
│ Jito Bundle Reject  │ 3 retries    │ Fallback to RPC direct       │
│ Flashbots Reject    │ 3 retries    │ Fallback to public mempool   │
└─────────────────────┴──────────────┴──────────────────────────────┘
```

---

## Performance

| Technique | Impact |
|-----------|--------|
| `uvloop` | 20-30% faster asyncio event loop |
| `orjson` | 10x faster JSON parse vs stdlib |
| `ProcessPoolExecutor` | Bypass Python GIL for math-heavy ops |
| Persistent `aiohttp` sessions | Reuse TCP connection, eliminate handshake |
| Price cache TTL 1s | Reduce RPC latency from ~200ms to ~0.1ms |
| Semaphore limiting | Prevent memory exhaustion under volatility |
| IPC provider fallback | Zero-latency for local node |

---

## Pre-Flight Checklist

### Phase 1: Offset Verification (BLOCKER)

```bash
pip install solana solders
python verify_raydium_offsets.py 58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2
```

- [ ] Compare output with [Solscan](https://solscan.io/account/58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2)
- [ ] If mismatch → edit `RAYDIUM_AMM_OFFSETS` in `main_final_v3.py` → repeat

### Phase 2: Environment Setup
- [ ] `.env` filled with RPC, private key, contract address
- [ ] `EXECUTOR_CONTRACT` deployed on testnet
- [ ] Testnet balance sufficient for gas + tips

### Phase 3: Dry Run
- [ ] Bot starts without crash
- [ ] WebSocket connects (3x listener active)
- [ ] State hydration completes
- [ ] Health check responds at `http://localhost:8080/health`
- [ ] Telegram test notification delivered

### Phase 4: Live Testnet
- [ ] Opportunity detected (profit < threshold, no execution)
- [ ] Or: execute 1 trade with `MIN_PROFIT_USD=0.01` to test flow
- [ ] Watchdog confirms tx within <60 seconds
- [ ] Dashboard log appears in SQLite

### Phase 5: Mainnet Graduation
- [ ] Switch RPC to mainnet
- [ ] Increase `MIN_PROFIT_USD` to $50+
- [ ] Set `MAX_CONCURRENT_EXECUTIONS=1` (safety mode)
- [ ] Monitor 24 hours before scaling up

---

## Monitoring

### Health Check
```bash
curl http://localhost:8080/health
```

Response:
```json
{
  "status": "healthy",
  "circuit_broken": false,
  "daily_pnl": 127.50,
  "total_trades": 42,
  "successful_trades": 38,
  "evm_pools_cached": 2,
  "solana_pools_cached": 2,
  "timestamp": "2026-06-17T21:00:00"
}
```

### Prometheus Metrics
```bash
curl http://localhost:8080/metrics
```

Output:
```
# HELP bot_daily_pnl Current daily P&L
# TYPE bot_daily_pnl gauge
bot_daily_pnl 127.50

# HELP bot_total_trades Total trades executed
# TYPE bot_total_trades counter
bot_total_trades 42
```

---

## Roadmap

| Item | Status | Priority |
|------|--------|----------|
| Raydium offset verification | 🔴 Pending | Critical |
| CEX hedge execution | 🟡 Detection only | Medium |
| Flashbots multi-tx bundles | 🟡 Single tx only | Low |
| Native Prometheus metrics | 🟡 Text format only | Low |
| Unit test coverage | 🔴 None | High |
| Integration test (mock RPC) | 🔴 None | High |

---

## Disclaimer

**This software is for educational and research purposes only.**

- Trading cryptocurrencies carries significant risk of loss
- Past performance does not guarantee future results
- MEV protection does not guarantee profit or prevent all forms of front-running
- Always test thoroughly on devnet/testnet before mainnet deployment
- The authors assume no liability for financial losses incurred through use of this software

---

<div align="center">

**Built with** Python · asyncio · Solana · Ethereum · WebSocket

*"In HFT, you don't need to be the fastest. You need to be fast enough, correct enough, and survive long enough to compound."*

</div>
