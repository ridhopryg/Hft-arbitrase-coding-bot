# Technical Code Documentation
## Penjelasan Tiap Modul dan Fungsi — main.py

---

## 1. IMPORT STACK

```python
import asyncio, websockets, orjson, os, signal, struct, base64, time, hashlib, sqlite3, random
from decimal import Decimal, getcontext
from typing import Dict, Any, Optional, Tuple, List, Set
from dotenv import load_dotenv
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor
from functools import wraps
import aiohttp
from aiohttp import web
```

**Penjelasan:**
- `asyncio` + `websockets` — Event loop dan WebSocket client untuk real-time stream
- `orjson` — Parser JSON 10x lebih cepat dari `json` standard library
- `struct` — Binary unpacking untuk decode Solana account data
- `base64` — Decode Solana WebSocket response encoding
- `Decimal` — Precision 50 digit untuk perhitungan arbitrage tanpa floating point error
- `ProcessPoolExecutor` — Bypass Python GIL untuk kalkulasi matematika berat
- `wraps` — Decorator utility untuk retry mechanism
- `aiohttp` — HTTP client async + web server untuk health check

---

## 2. RETRY DECORATOR (`@async_retry`)

```python
def async_retry(max_attempts=3, base_delay=1.0, max_delay=10.0, exceptions=(Exception,)):
```

**Fungsi:** Wrapper untuk semua fungsi async yang memanggil RPC eksternal.

**Logika:**
1. Try execute fungsi
2. Jika exception yang diizinkan terjadi → tunggu `base_delay * 2^(attempt-1)` + random jitter 10%
3. Ulangi sampai `max_attempts`
4. Jika masih gagal → raise exception ke caller

**Kenapa penting:** RPC node bisa timeout, rate limit, atau temporary down. Tanpa retry, bot akan crash atau miss opportunity.

---

## 3. CONFIGURATION (`Config`)

```python
class Config:
    MIN_PROFIT_USD = float(os.getenv("MIN_PROFIT_USD", 15.0))
    SOLANA_RPC = os.getenv("SOLANA_RPC_URL", "https://api.devnet.solana.com")
    ...
```

**Pattern:** Single source of truth. Semua parameter di-load dari environment variable dengan default value yang aman untuk devnet.

**Validasi Runtime:**
- `SOLANA_PRIVATE_KEY` — dicek panjang minimal 30 karakter
- `EVM_PRIVATE_KEY` — dicek prefix `0x` dan panjang 66 karakter

**Kenapa tidak hardcode:** Untuk deploy di berbagai environment (devnet/testnet/mainnet) tanpa ubah kode.

---

## 4. SOLANA ON-CHAIN LAYOUT

```python
TOKEN_PROGRAM_ID = SolanaPubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
RAYDIUM_AMM_PROGRAM = SolanaPubkey.from_string("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8")
```

**Penjelasan:**
- `TOKEN_PROGRAM_ID` — Program SPL Token untuk semua token account di Solana
- `RAYDIUM_AMM_PROGRAM` — Program ID Raydium AMM v4
- `SERUM_DEX_PROGRAM` — Program ID Serum DEX (orderbook Raydium)

**Fungsi `find_associated_token_address`:**
- Menggunakan `find_program_address` dengan seeds: `[owner, token_program, mint]`
- Hasil: ATA (Associated Token Address) untuk wallet + token mint tertentu

**OFFSETS:**
- `RAYDIUM_AMM_OFFSETS` — Lokasi byte di account data Raydium pool
- `SERUM_MARKET_OFFSETS` — Lokasi byte di Serum market account

**WARNING:** Offset 240 (amm_authority) belum diverifikasi on-chain. WAJIB jalankan `verify_raydium_offsets.py` sebelum deploy.

---

## 5. DATA STRUCTURES

```python
@dataclass
class SolanaPoolState:
    pool_id: str
    amm_accounts: Dict[str, SolanaPubkey]
    serum_accounts: Dict[str, SolanaPubkey]
    coin_mint: Optional[SolanaPubkey]
    pc_mint: Optional[SolanaPubkey]
    coin_vault: Optional[str]
    pc_vault: Optional[str]
    reserves: Dict[str, int]
```

**Penjelasan:**
- `amm_accounts` — Mapping nama field ke Pubkey (authority, open_orders, pool_token, serum_market)
- `serum_accounts` — Mapping Serum orderbook (bids, asks, event_queue, vaults)
- `reserves` — Balance x (coin) dan y (pc) untuk kalkulasi harga

**Kenapa dataclass:** Immutable-ish structure dengan auto-generated `__init__`, `__repr__`, type-safe.

---

## 6. PRICE CACHE (`PriceCache`)

```python
class PriceCache:
    async def get(self, chain: str, price_id: str) -> float
```

**Alur:**
1. Cek cache dengan key `chain:price_id`
2. Jika TTL < 1 detik → return cached value
3. Jika expired → fetch dari PriceFeedEngine → store → return

**Kenapa TTL 1 detik:** Harga berubah setiap block (400ms di Solana, 12s di Ethereum). Cache lebih dari 1 detik bisa menyebabkan perhitungan profit salah (stale price).

---

## 7. PRICE FEED ENGINE (`PriceFeedEngine`)

```python
class PriceFeedEngine:
    async def get_solana_price(self, pyth_price_id: str) -> float
    async def get_evm_price(self, chainlink_address: str) -> float
    async def _get_twap_fallback(self, pool_address: str) -> float
```

**Hierarki Fallback:**
1. Pyth Network (Solana) / Chainlink (EVM) — Primary oracle
2. Uniswap V3 TWAP (`slot0.sqrtPriceX96`) — Fallback jika oracle down

**TWAP Formula:**
```
price = (sqrtPriceX96 / 2^96)^2
```

**Kenapa fallback:** Oracle downtime = bot buta = miss opportunity atau worse, execute dengan harga salah.

---

## 8. PATH FINDER (`PathFinder`)

### 8.1 Bounded BFS (`find_best_circular_arbitrage`)

```python
def find_best_circular_arbitrage(self, start_token: str, max_hops: int = 3)
```

**Algoritma:**
- Queue-based BFS dengan constraint `max_hops`
- Setiap edge: `amount_out = (amount_in * fee * reserve_out) / (reserve_in + amount_in * fee)`
- Return path dengan net profit maksimal

**Complexity:** O(V + E) untuk bounded BFS — feasible untuk real-time HFT.

### 8.2 Bellman-Ford (`find_negative_cycle`)

```python
def find_negative_cycle(self, start_token: str)
```

**Algoritma:**
- Edge weight = `-ln(exchange_rate)`
- Relax edges (V-1) kali
- Cek negative cycle di iterasi V

**Kenapa `-ln(rate)`:** Negative cycle = arbitrage opportunity (kembali ke token awal dengan jumlah lebih banyak).

---

## 9. QUANTITATIVE ENGINE (`QuantitativeEngine`)

```python
@staticmethod
def calculate_optimal_arbitrage(r1_x, r1_y, r2_x, r2_y, fee_bps) -> Tuple[Optional[int], int]
```

**Formula Matematis:**
```
f = (10000 - fee_bps) / 10000
optimal = (√(r1x·r2x·r1y·r2y)·f - r1x·r2y) / (r2y·f)
```

**Asal formula:** Turunan dari constant product AMM (x*y=k) untuk mencari input yang memaksimalkan profit.

**GIL Workaround:**
```python
@classmethod
async def calculate_async(cls, r1_x, r1_y, r2_x, r2_y, fee):
    executor = await cls._get_executor()
    return await loop.run_in_executor(executor, ...)
```

Python GIL membuat thread-blocking untuk CPU-intensive task. `ProcessPoolExecutor` menjalankan kalkulasi di subprocess terpisah, freeing event loop untuk handle WebSocket/HTTP.

---

## 10. NONCE MANAGER (`NonceManager`)

```python
class NonceManager:
    async def get_nonce(self) -> int
    async def decrement_nonce()
    async def confirm_nonce()
    async def sync_nonce()
```

**Problem:** HFT mengirim banyak tx bersamaan. Nonce collision = tx rejected.

**Solusi:**
- `get_nonce()` — Return `base_nonce + pending_count`, lalu increment pending
- `confirm_nonce()` — Decrement pending setelah tx confirmed (tidak decrement base)
- `decrement_nonce()` — Rollback pending jika tx fail sebelum submit
- `sync_nonce()` — Resync dengan on-chain state untuk recovery

---

## 11. MEV DISPATCHER (`MEVDispatcher`)

```python
class MEVDispatcher:
    async def send_transaction(self, signed_tx) -> Tuple[str, bool]
```

**Flow:**
1. Siapkan Flashbots bundle: `eth_sendBundle` dengan target block = current + 1
2. Sign bundle dengan `encode_defunct(keccak(payload))` — EIP-191 compliant
3. Kirim ke Flashbots Relay dengan header `X-Flashbots-Signature`
4. Jika reject/error → fallback ke public mempool

**Return:** `(tx_hash, is_private)`
- `is_private=True` — Bundle masuk ke Flashbots (tidak visible di public mempool)
- `is_private=False` — Fallback ke public (terlihat di mempool, rentan front-run)

---

## 12. JITO BUNDLE SENDER (`JitoBundleSender`)

```python
class JitoBundleSender:
    async def send_bundle(self, tx_base64: str, tip_account: str) -> Tuple[bool, str]
```

**Flow:**
1. Encode tx ke base64
2. Kirim POST ke `JITO_BUNDLE_URL` dengan JSON-RPC format
3. Parameter: `[tx_base64]` + tip account
4. Retry 3x dengan exponential backoff

**Fallback:** Jika Jito reject, kirim langsung via Solana RPC (`send_transaction`).

**Persistent Session:** Menggunakan `aiohttp.ClientSession` yang sama untuk semua request — menghindari TCP handshake overhead.

---

## 13. TRANSACTION WATCHDOG (`TransactionWatchdog`)

```python
class TransactionWatchdog:
    async def _watch_loop(self)
    async def _speed_up_transaction(self, nonce, tx_params)
```

**Loop:** Setiap 5 detik, cek semua pending tx:
- Jika confirmed → log success, remove dari tracking
- Jika stuck >60 detik → speed up dengan gas bump 20%

**Speed Up:**
```python
new_gas = int(old_gas * 1.2)
new_priority = int(old_priority * 1.2)
```

Kirim ulang tx dengan nonce sama tapi gas lebih tinggi — menggantikan tx lama di mempool.

---

## 14. RISK MANAGER (`RiskManager`)

```python
class RiskManager:
    def check_gas_price(self, gas_price_gwei) -> bool
    def check_daily_limit(self, profit_usd) -> bool
    def record_trade(self, profit_usd, success)
```

**State Machine:**
- `daily_profit_usd` — Akumulasi P&L harian (reset tiap 24 jam)
- `consecutive_losses` — Counter loss berturut-turut
- `circuit_broken` — Boolean flag, ketika True semua execution di-block

**Trigger Circuit Breaker:**
1. Daily loss > $500
2. 5 consecutive losses
3. Cooldown: 1 jam (3600 detik)

---

## 15. JITO TIP OPTIMIZER (`JitoTipOptimizer`)

```python
class JitoTipOptimizer:
    async def fetch_tip_floor(self) -> int
    async def get_dynamic_tip(self) -> int
```

**Sumber:** API `bundles.jito.wtf/api/v1/tip-floor`

**Logika:**
1. Fetch floor tip (lamports per signature)
2. Cache selama 5 detik
3. Return `max(floor * 1.2, 10_000)` — 20% di atas floor untuk memastikan bundle masuk

**Kenapa dynamic:** Jito tip floor berubah berdasarkan congestion. Tip terlalu rendah = bundle di-skip. Tip terlalu tinggi = margin profit berkurang.

---

## 16. MEMPOOL SCANNER (`MempoolScanner`)

```python
class MempoolScanner:
    async def _is_target_swap(self, tx: dict) -> Tuple[bool, List[str]]
```

**Deteksi:**
- Subscribe ke `alchemy_pendingTransactions` via WebSocket
- Cek `to` address — apakah router DEX (Uniswap V2/V3)
- Parse method ID dari `input` data:
  - `0x38ed1739` — swapExactTokensForTokens
  - `0x8803dbee` — swapTokensForExactTokens
  - `0x7ff36ab5` — swapExactETHForTokens

**Backrun Trigger:** Jika swap terdeteksi, cari pool address dalam input data lalu trigger re-evaluasi arbitrage untuk pool tersebut.

---

## 17. CROSS-CHAIN HEDGER (`CrossChainHedger`)

```python
class CrossChainHedger:
    async def get_binance_price(self, symbol: str) -> Optional[float]
    async def arbitrage_loop(self)
```

**Status:** DETECTION-ONLY. Belum ada eksekusi CEX.

**Flow:**
1. Fetch harga Binance (REST API)
2. Fetch harga on-chain (Pyth)
3. Hitung spread: `abs(binance - onchain) / onchain`
4. Jika spread > 0.5% → log opportunity

**TODO:** Implementasi order placement Binance + balance sync.

---

## 18. DASHBOARD ENGINE (`DashboardEngine`)

```python
class DashboardEngine:
    async def log_trade(self, chain, pool, amount_in, profit_usd, gas_cost_usd, success, tx_hash)
    async def daily_report(self)
    async def send_telegram_notification(self, message)
```

**SQLite Schema:**
```sql
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    chain TEXT,
    pool TEXT,
    amount_in REAL,
    profit_usd REAL,
    gas_cost_usd REAL,
    success INTEGER,
    tx_hash TEXT
);
```

**Non-blocking:** Semua query SQLite di-wrap dengan `run_in_executor(None, ...)` agar tidak block event loop.

**Telegram:** Report otomatis setiap 6 jam (21600 detik) dengan format HTML.

---

## 19. HEALTH CHECK SERVER (`HealthCheckServer`)

```python
class HealthCheckServer:
    async def health_handler(self, request)   # GET /health
    async def metrics_handler(self, request)  # GET /metrics
```

**Endpoints:**
- `/health` — JSON status: circuit breaker, PnL, pool count, timestamp
- `/metrics` — Prometheus text format: `bot_daily_pnl`, `bot_total_trades`, `bot_circuit_breaker`

**Kenapa Prometheus:** Industri standard untuk monitoring. Bisa di-scrape oleh Grafana untuk dashboard visual.

---

## 20. HFTOrchestrator (Main Controller)

```python
class HFTOrchestrator:
    def __init__(self)
    async def hydrate_all(self, evm_pools, sol_pools)
    async def evaluate_and_execute(self, chain, pool_id, pool_data)
    async def _execute_evm(self, amount_in, pool_id, pool_data)
    async def _execute_solana(self, amount_in, pool_id)
    async def start(self)
    async def close(self)
```

**Lifecycle:**
1. `__init__` — Inisialisasi semua komponen (connection, engine, manager)
2. `hydrate_all` — Fetch initial state dari on-chain (cold start)
3. `start` — Jalankan semua listener (WebSocket) sebagai background task
4. `evaluate_and_execute` — Triggered oleh WebSocket update, lakukan profit calc + risk check + execution
5. `close` — Graceful shutdown: cancel task, close connection, cleanup executor

**Task Management:**
- `_create_task(coro)` — Wrapper dengan tracking di `Set[asyncio.Task]`
- `close()` — Cancel semua task, `gather` dengan `return_exceptions=True`

**Semaphores:**
- `eval_semaphore` — Limit 10 concurrent evaluations (anti-memory-leak)
- `exec_semaphore` — Limit 3 concurrent executions (capital preservation)

---

## 21. EVM EXECUTION FLOW (`_execute_evm`)

```python
async def _execute_evm(self, amount_in: int, pool_id: str, pool_data: dict)
```

**Step-by-Step:**
1. Load executor contract ABI
2. Hitung `amount_out_min` dengan slippage 0.5%
3. Fetch dynamic gas: `fee_history.baseFee + max_priority_fee`
4. Cek gas price vs `MAX_GAS_GWEI`
5. Get nonce dari `NonceManager`
6. Encode `executeArbitrage` call dengan `minProfit` estimate
7. `estimate_gas` untuk validasi
8. Recalculate `minProfit` dengan actual gas cost
9. `eth_call` untuk simulasi
10. Sign tx dengan `Account.sign_transaction`
11. Kirim via `MEVDispatcher` (Flashbots atau public)
12. Jika public → add ke `TransactionWatchdog`
13. Log trade ke SQLite + Telegram

---

## 22. SOLANA EXECUTION FLOW (`_execute_solana`)

```python
async def _execute_solana(self, amount_in: int, pool_id: str)
```

**Step-by-Step:**
1. Load pool state dari cache
2. Get dynamic tip dari `JitoTipOptimizer`
3. Buat compute budget instructions (limit 100k, price 10k microlamports)
4. Build Raydium swap instruction dengan 15 account metas
5. Build Jito tip transfer instruction
6. Compile `MessageV0` dengan 4 instructions
7. Sign dengan `VersionedTransaction`
8. `simulate_transaction` dengan `sig_verify=True`
9. Encode ke base64
10. Kirim via `JitoBundleSender`
11. Jika reject → fallback ke RPC `send_transaction`
12. Log trade ke SQLite

---

## 23. DATA FLOW DIAGRAM

```
[WebSocket Update]
       |
       v
[Update Reserves in Cache]
       |
       v
[PriceCache.get()] — TTL 1s
       |
       v
[QuantitativeEngine.calculate_async()] — ProcessPool
       |
       v
[RiskManager.check_gas_price()]
[RiskManager.check_daily_limit()]
       |
       v
[evaluate_and_execute()] — Semaphore limit
       |
       v
[EVM] —> MEVDispatcher —> Flashbots/Public
[Solana] —> JitoBundleSender —> Jito/RPC
       |
       v
[TransactionWatchdog] —> Track 60s —> Speed up if stuck
       |
       v
[DashboardEngine.log_trade()] —> SQLite + Telegram
```

---

## 24. ERROR HANDLING STRATEGY

| Layer | Strategy | Fallback |
|-------|----------|----------|
| RPC Call | `@async_retry` 3x | Log warning, skip cycle |
| Gas Estimation | Catch exception | Abort execution |
| Simulation Fail | Return immediately | Do not submit tx |
| Bundle Reject | Retry 3x | Public mempool |
| Stuck Tx | Gas bump 20% | Speed up tx |
| Circuit Breaker | Block all execution | Auto resume after cooldown |
| WebSocket Disconnect | Sleep 2s, reconnect | Infinite retry loop |

---

## 25. STATE MANAGEMENT

| State | Location | Persistence | Sync |
|-------|----------|-------------|------|
| Pool Reserves | `sol_pool_cache`, `evm_pool_cache` | Memory | WebSocket real-time |
| Prices | `PriceCache` | Memory (TTL 1s) | RPC on miss |
| Nonce | `NonceManager` | Memory | On-chain sync on init |
| Daily P&L | `RiskManager` | Memory | Reset every 24h |
| Trade History | SQLite | Disk | Async write |
| Circuit Breaker | `RiskManager` | Memory | Manual/auto resume |

---

*Dokumen ini menjelaskan setiap baris kode penting di `main.py`. Untuk pertanyaan spesifik, refer ke section terkait.*
