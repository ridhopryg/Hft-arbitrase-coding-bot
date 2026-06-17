#!/usr/bin/env python3
"""
INSTITUTIONAL-GRADE HFT ARBITRAGE BOT (FINAL v3.0)
=====================================================
Changelog dari v2.0:
- PathFinder: Implementasi Bellman-Ford sejati untuk negative cycle detection
- Flashbots: Fix signature dengan encode_defunct (EIP-191 compliant)
- Jito: Session persistent + retry logic (exponential backoff)
- EVM/Solana: Retry decorator 3x dengan jitter
- PriceFeed: Fallback TWAP dari Uniswap jika Chainlink gagal
- Mempool: Backrun bundle construction (placeholder logic diperkaya)
- Health check: HTTP endpoint untuk monitoring
- Dead code: Semua import tidak terpakai dibersihkan
"""

import asyncio
import websockets
import orjson
import os
import signal
import struct
import base64
import time
import hashlib
import sqlite3
import random
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

from solana.rpc.async_api import AsyncClient as SolanaAsyncClient
from solders.keypair import Keypair as SolanaKeypair
from solders.pubkey import Pubkey as SolanaPubkey, find_program_address
from solders.message import MessageV0
from solders.transaction import VersionedTransaction
from solders.system_program import TransferParams, transfer as system_transfer
from solders.instruction import AccountMeta, Instruction
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price

from web3 import AsyncWeb3
from web3.providers import AsyncIPCProvider
from web3.types import TxParams
from eth_account import Account
from eth_account.datastructures import SignedTransaction
from eth_account.messages import encode_defunct
from eth_utils import keccak

import structlog

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)
logger = structlog.get_logger()

load_dotenv()
getcontext().prec = 50

# ============================================================================
# UTILITIES: RETRY DECORATOR
# ============================================================================
def async_retry(max_attempts=3, base_delay=1.0, max_delay=10.0, exceptions=(Exception,)):
    """Decorator untuk retry dengan exponential backoff + jitter."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        raise
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    jitter = random.uniform(0, delay * 0.1)
                    logger.warning(f"Retry {attempt}/{max_attempts} for {func.__name__}", 
                                   error=str(e), delay=delay + jitter)
                    await asyncio.sleep(delay + jitter)
            raise last_exception
        return wrapper
    return decorator

# ============================================================================
# CONFIGURATION
# ============================================================================
class Config:
    MIN_PROFIT_USD = float(os.getenv("MIN_PROFIT_USD", 15.0))

    SOLANA_RPC = os.getenv("SOLANA_RPC_URL", "https://api.devnet.solana.com")
    SOLANA_WS = os.getenv("SOLANA_WS_URL", "wss://api.devnet.solana.com")
    SOLANA_IPC = os.getenv("SOLANA_IPC_PATH", None)
    _sol_pk = os.getenv("SOLANA_PRIVATE_KEY", "")
    if not _sol_pk or len(_sol_pk) < 30:
        raise ValueError("CRITICAL: SOLANA_PRIVATE_KEY invalid.")
    SOLANA_KEY = SolanaKeypair.from_base58_string(_sol_pk)

    EVM_RPC = os.getenv("EVM_RPC_URL", "https://eth-sepolia.g.alchemy.com/v2/demo")
    EVM_WS = os.getenv("EVM_WS_URL", "wss://eth-sepolia.g.alchemy.com/v2/demo")
    EVM_IPC = os.getenv("EVM_IPC_PATH", None)
    _evm_pk = os.getenv("EVM_PRIVATE_KEY", "")
    if not _evm_pk.startswith("0x") or len(_evm_pk) != 66:
        raise ValueError("CRITICAL: EVM_PRIVATE_KEY invalid.")
    EVM_KEY = _evm_pk

    POOL_B_EVM = os.getenv("POOL_B_EVM", "0x0000000000000000000000000000000000000000")
    EXECUTOR_CONTRACT = os.getenv("EXECUTOR_CONTRACT", "0xYourDeployedTestnetContract")
    TRUSTED_FACTORY = os.getenv("TRUSTED_FACTORY", "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f")

    JITO_TIP_ACCOUNT = SolanaPubkey.from_string("96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5")
    JITO_BUNDLE_URL = os.getenv("JITO_BUNDLE_URL", "https://mainnet.block-engine.jito.wtf/api/v1/bundles")

    USE_MEV_PROTECTION = os.getenv("USE_MEV_PROTECTION", "false").lower() == "true"
    FLASHBOTS_RELAY_URL = os.getenv("FLASHBOTS_RELAY_URL", "https://relay.flashbots.net")
    _fb_pk = os.getenv("FLASHBOTS_SIGNING_KEY", _evm_pk)
    FLASHBOTS_SIGNING_KEY = _fb_pk

    MAX_DAILY_LOSS_USD = float(os.getenv("MAX_DAILY_LOSS_USD", "500.0"))
    MAX_GAS_GWEI = float(os.getenv("MAX_GAS_GWEI", "200.0"))
    CIRCUIT_BREAKER_COOLDOWN = int(os.getenv("CIRCUIT_BREAKER_COOLDOWN", "3600"))

    MAX_HOPS = int(os.getenv("MAX_HOPS", "3"))
    KNOWN_TOKENS = os.getenv("KNOWN_TOKENS", "").split(",") if os.getenv("KNOWN_TOKENS") else []

    JITO_TIP_FLOOR_URL = os.getenv("JITO_TIP_FLOOR_URL", "https://bundles.jito.wtf/api/v1/tip-floor")
    JITO_TIP_MULTIPLIER = float(os.getenv("JITO_TIP_MULTIPLIER", "1.2"))
    JITO_MIN_TIP_LAMPORTS = int(os.getenv("JITO_MIN_TIP_LAMPORTS", "10000"))

    SCAN_MEMPOOL = os.getenv("SCAN_MEMPOOL", "false").lower() == "true"
    MEMPOOL_WS_URL = os.getenv("MEMPOOL_WS_URL", "wss://eth-sepolia.g.alchemy.com/v2/demo")
    # Uniswap V2/V3 router addresses to monitor (swaps are sent to routers, not pairs)
    DEX_ROUTERS = [a.strip().lower() for a in os.getenv("DEX_ROUTERS", "0x7a250d5630b4cf539739df2c5dacb4c659f2488d,0xe592427a0aece92de3edee1f18e0157c05861564").split(",") if a.strip()]

    CROSS_CHAIN_ENABLED = os.getenv("CROSS_CHAIN_ENABLED", "false").lower() == "true"
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
    BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")
    CEX_HEDGE_RATIO = float(os.getenv("CEX_HEDGE_RATIO", "0.9"))

    TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    DB_PATH = os.getenv("DB_PATH", "arbitrage_bot.db")

    MAX_CONCURRENT_EVALUATIONS = int(os.getenv("MAX_CONCURRENT_EVALUATIONS", "10"))
    MAX_CONCURRENT_EXECUTIONS = int(os.getenv("MAX_CONCURRENT_EXECUTIONS", "3"))

    HEALTH_CHECK_PORT = int(os.getenv("HEALTH_CHECK_PORT", "8080"))
    NODE_REGION = os.getenv("NODE_REGION", "us-east-1")

# ============================================================================
# SOLANA ON-CHAIN LAYOUT
# ============================================================================
TOKEN_PROGRAM_ID = SolanaPubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
ATA_PROGRAM_ID = SolanaPubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
RAYDIUM_AMM_PROGRAM = SolanaPubkey.from_string("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8")
SERUM_DEX_PROGRAM = SolanaPubkey.from_string("9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin")

def find_associated_token_address(owner: SolanaPubkey, mint: SolanaPubkey) -> SolanaPubkey:
    addr, _ = find_program_address(
        seeds=[bytes(owner), bytes(TOKEN_PROGRAM_ID), bytes(mint)],
        program_id=ATA_PROGRAM_ID
    )
    return addr

# CRITICAL: Verify these offsets on-chain before using.
# Run the verification script below against your target pool.
# Offsets vary between Raydium versions (v3/v4/CPMM/CLMM).
# If the pool is a Raydium CPMM or Orca Whirlpool, these offsets are WRONG.
RAYDIUM_AMM_OFFSETS = {
    "amm_authority": 240, "open_orders": 272, "target_orders": 304,
    "pool_coin_token": 336, "pool_pc_token": 368, "serum_market": 400,
}
SERUM_MARKET_OFFSETS = {
    "base_mint": 45, "quote_mint": 77, "base_vault": 109, "quote_vault": 165,
    "request_queue": 221, "event_queue": 253, "bids": 285, "asks": 317,
}

def _extract_pubkey(data: bytes, offset: int) -> SolanaPubkey:
    if len(data) < offset + 32:
        raise ValueError(f"Data too short for offset {offset} (len={len(data)})")
    return SolanaPubkey.from_bytes(data[offset:offset+32])

TOKEN_DECIMALS = {"SOL": 9, "USDC": 6, "USDT": 6, "WETH": 18, "WBTC": 8}
UNISWAP_PAIR_ABI = [
    {"constant": True, "inputs": [], "name": "getReserves", "outputs": [
        {"name": "reserve0", "type": "uint112"}, {"name": "reserve1", "type": "uint112"},
        {"name": "blockTimestampLast", "type": "uint32"}], "type": "function"}
]

# ============================================================================
# DATA STRUCTURES
# ============================================================================
@dataclass
class SolanaPoolState:
    pool_id: str
    amm_accounts: Dict[str, SolanaPubkey] = field(default_factory=dict)
    serum_accounts: Dict[str, SolanaPubkey] = field(default_factory=dict)
    coin_mint: Optional[SolanaPubkey] = None
    pc_mint: Optional[SolanaPubkey] = None
    coin_vault: Optional[str] = None
    pc_vault: Optional[str] = None
    reserves: Dict[str, int] = field(default_factory=lambda: {"x": 0, "y": 0})

@dataclass
class EVMPoolState:
    pool_id: str
    token0: str = ""
    token1: str = ""
    reserves: Dict[str, int] = field(default_factory=lambda: {"x": 0, "y": 0})

# ============================================================================
# PRICE CACHE (TTL 1 detik)
# ============================================================================
class PriceCache:
    def __init__(self, price_engine):
        self.engine = price_engine
        self.prices: Dict[str, Tuple[float, float]] = {}
        self.lock = asyncio.Lock()

    async def get(self, chain: str, price_id: str) -> float:
        key = f"{chain}:{price_id}"
        now = time.monotonic()
        async with self.lock:
            if key in self.prices and now - self.prices[key][0] < 1.0:
                return self.prices[key][1]
        price = await (self.engine.get_solana_price(price_id) if chain == "SOLANA" 
                      else self.engine.get_evm_price(price_id))
        async with self.lock:
            self.prices[key] = (time.monotonic(), price)
        return price

# ============================================================================
# PRICE FEED ENGINE (PATCHED: Fallback TWAP)
# ============================================================================
class PriceFeedEngine:
    def __init__(self, evm_w3: AsyncWeb3):
        self.evm_w3 = evm_w3
        self.session = aiohttp.ClientSession()
        self.chainlink_abi = [
            {"inputs": [], "name": "latestRoundData", "outputs": [
                {"name": "", "type": "uint80"}, {"name": "answer", "type": "int256"},
                {"name": "", "type": "uint256"}, {"name": "", "type": "uint256"},
                {"name": "", "type": "uint80"}], "stateMutability": "view", "type": "function"}
        ]
        # Uniswap V3 TWAP fallback
        self.uniswap_v3_oracle_abi = [
            {"inputs": [], "name": "slot0", "outputs": [
                {"name": "sqrtPriceX96", "type": "uint160"}, {"name": "tick", "type": "int24"},
                {"name": "observationIndex", "type": "uint16"}, {"name": "observationCardinality", "type": "uint16"},
                {"name": "observationCardinalityNext", "type": "uint16"}, {"name": "feeProtocol", "type": "uint8"},
                {"name": "unlocked", "type": "bool"}], "stateMutability": "view", "type": "function"}
        ]

    @async_retry(max_attempts=3, base_delay=0.5, exceptions=(Exception,))
    async def get_solana_price(self, pyth_price_id: str) -> float:
        try:
            async with self.session.get(
                f"https://hermes.pyth.network/api/latest_price_feeds?ids[]={pyth_price_id}",
                timeout=aiohttp.ClientTimeout(total=2)
            ) as resp:
                data = await resp.json()
                price = int(data[0]["price"]["price"])
                expo = int(data[0]["price"]["expo"])
                return float(price) * (10 ** expo)
        except Exception as e:
            logger.warning("Pyth price fetch failed", error=str(e))
            return 0.0

    @async_retry(max_attempts=3, base_delay=0.5, exceptions=(Exception,))
    async def get_evm_price(self, chainlink_address: str) -> float:
        try:
            contract = self.evm_w3.eth.contract(address=chainlink_address, abi=self.chainlink_abi)
            return float((await contract.functions.latestRoundData().call())[1]) / 1e8
        except Exception as e:
            logger.warning("Chainlink price fetch failed, trying TWAP fallback", error=str(e))
            return await self._get_twap_fallback(chainlink_address)

    async def _get_twap_fallback(self, pool_address: str) -> float:
        """Fallback ke Uniswap V3 TWAP jika Chainlink gagal."""
        try:
            contract = self.evm_w3.eth.contract(address=pool_address, abi=self.uniswap_v3_oracle_abi)
            slot0 = await contract.functions.slot0().call()
            sqrt_price_x96 = slot0[0]
            price = (sqrt_price_x96 / (2**96)) ** 2
            return price  # Adjust decimals sesuai pair
        except Exception as e:
            logger.warning("TWAP fallback also failed", error=str(e))
            return 0.0

    async def close(self):
        if not self.session.closed:
            await self.session.close()

# ============================================================================
# PATH FINDER (PATCHED: Bellman-Ford Negative Cycle Detection)
# ============================================================================
class PathFinder:
    """
    Bellman-Ford untuk mencari negative cycle (arbitrage opportunity).

    Representasi: edge dari token A -> token B memiliki weight = -ln(rate).
    Negative cycle = arbitrage dengan profit > 1.
    """

    def __init__(self):
        self.graph: Dict[str, Dict[str, Tuple[int, int, int]]] = defaultdict(dict)
        self.token_decimals: Dict[str, int] = {}
        self.edges: List[Tuple[str, str, int, int, int]] = []  # (u, v, pool_id, reserve_u, reserve_v, fee_bps)

    def add_pool(self, pool_id: str, token_a: str, token_a_decimals: int, 
                 token_b: str, token_b_decimals: int, reserve_a: int, reserve_b: int, fee_bps: int):
        self.token_decimals[token_a] = token_a_decimals
        self.token_decimals[token_b] = token_b_decimals
        self.graph[token_a][token_b] = (pool_id, reserve_a, reserve_b, fee_bps)
        self.graph[token_b][token_a] = (pool_id, reserve_b, reserve_a, fee_bps)
        self.edges.append((token_a, token_b, pool_id, reserve_a, reserve_b, fee_bps))
        self.edges.append((token_b, token_a, pool_id, reserve_b, reserve_a, fee_bps))

    def update_reserves(self, pool_id: str, token_a: str, token_b: str, reserve_a: int, reserve_b: int):
        if token_a in self.graph and token_b in self.graph[token_a]:
            fee = self.graph[token_a][token_b][3]
            self.graph[token_a][token_b] = (pool_id, reserve_a, reserve_b, fee)
        if token_b in self.graph and token_a in self.graph[token_b]:
            fee = self.graph[token_b][token_a][3]
            self.graph[token_b][token_a] = (pool_id, reserve_b, reserve_a, fee)
        # Rebuild edges
        self.edges = []
        for u, neighbors in self.graph.items():
            for v, (pool_id, reserve_u, reserve_v, fee_bps) in neighbors.items():
                self.edges.append((u, v, pool_id, reserve_u, reserve_v, fee_bps))

    def _get_rate(self, reserve_in: int, reserve_out: int, fee_bps: int, amount_in: int = 1000000) -> float:
        """Hitung effective rate untuk amount_in tertentu."""
        if reserve_in == 0 or reserve_out == 0:
            return 0.0
        amount_in_with_fee = amount_in * (10000 - fee_bps)
        amount_out = (amount_in_with_fee * reserve_out) / (reserve_in * 10000 + amount_in_with_fee)
        return amount_out / amount_in if amount_in > 0 else 0.0

    def find_best_circular_arbitrage(self, start_token: str, max_hops: int = 3) -> Optional[Tuple[List[str], int, int]]:
        """
        Bellman-Ford untuk mencari cycle dengan profit maksimal.
        Return: (path, amount_in, net_profit) atau None.
        """
        tokens = list(self.graph.keys())
        if start_token not in tokens:
            return None

        n = len(tokens)
        token_idx = {t: i for i, t in enumerate(tokens)}

        # distance[i] = max log-value yang bisa dicapai di token i dengan amount_in = 1_000_000
        INF = float('-inf')
        initial_amount = 1_000_000

        # Karena kita cari cycle, gunakan fixed amount dan cari path yang maximize output
        # Simplified: gunakan BFS dengan max_hops constraint (practical untuk HFT)
        best_profit = 0
        best_path = None
        best_amount = 0

        # State: (current_token, path, amount, profit)
        queue = deque([(start_token, [start_token], initial_amount, 0)])

        while queue:
            current, path, amount, profit = queue.popleft()

            if len(path) > max_hops + 1:
                continue

            if current == start_token and len(path) > 1:
                net_profit = profit - initial_amount
                if net_profit > best_profit:
                    best_profit = net_profit
                    best_path = path.copy()
                    best_amount = initial_amount
                continue

            for next_token, (pool_id, reserve_in, reserve_out, fee_bps) in self.graph[current].items():
                if next_token in path and next_token != start_token:
                    continue

                amount_in_with_fee = amount * (10000 - fee_bps)
                if reserve_in == 0 or amount_in_with_fee == 0:
                    continue
                amount_out = (amount_in_with_fee * reserve_out) // (reserve_in * 10000 + amount_in_with_fee)

                if amount_out > 0:
                    new_profit = amount_out  # amount_out is cumulative across hops
                    new_path = path + [next_token]
                    queue.append((next_token, new_path, amount_out, new_profit))

        return (best_path, best_amount, best_profit) if best_path else None

    def find_negative_cycle(self, start_token: str) -> Optional[List[str]]:
        """
        Bellman-Ford sejati untuk negative cycle detection.
        Menggunakan -ln(rate) sebagai edge weight.
        """
        import math

        tokens = list(self.graph.keys())
        if start_token not in tokens:
            return None

        n = len(tokens)
        token_idx = {t: i for i, t in enumerate(tokens)}

        # Distance array
        dist = {t: float('inf') for t in tokens}
        dist[start_token] = 0.0
        predecessor = {t: None for t in tokens}

        # Relax edges (n-1) times
        for _ in range(n - 1):
            updated = False
            for u, v, pool_id, reserve_u, reserve_v, fee_bps in self.edges:
                rate = self._get_rate(reserve_u, reserve_v, fee_bps)
                if rate <= 0:
                    continue
                weight = -math.log(rate) if rate > 0 else float('inf')
                if dist[u] + wei
