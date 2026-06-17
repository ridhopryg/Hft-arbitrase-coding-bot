#!/usr/bin/env python3
"""
Raydium AMM Offset Verification Tool
====================================
Run this BEFORE testnet deployment. No private key required.

Usage:
    python verify_raydium_offsets.py [POOL_ADDRESS] [--rpc URL]

Example:
    python verify_raydium_offsets.py 58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2
"""

import asyncio
import argparse
import sys
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey

# Offsets from main_final_v3.py
OFFSETS = {
    "amm_authority": 240,
    "open_orders": 272,
    "target_orders": 304,
    "pool_coin_token": 336,
    "pool_pc_token": 368,
    "serum_market": 400,
}

EXPECTED_MAINNET = {
    # Fill these after checking solscan.io for your pool
    # "amm_authority": "7u...",
}

async def verify(pool_address: str, rpc_url: str):
    client = AsyncClient(rpc_url)
    pool = Pubkey.from_string(pool_address)

    print(f"Pool:     {pool_address}")
    print(f"RPC:      {rpc_url}")
    print(f"Solscan:  https://solscan.io/account/{pool_address}")
    print("=" * 70)

    try:
        resp = await client.get_account_info(pool)
    except Exception as e:
        print(f"ERROR: RPC call failed: {e}")
        sys.exit(1)

    if not resp.value:
        print("ERROR: Account not found. Check address and network.")
        sys.exit(1)

    data = resp.value.data
    print(f"Data length: {len(data)} bytes")
    print()

    all_match = True
    for name, offset in OFFSETS.items():
        end = offset + 32
        if end > len(data):
            print(f"  ❌ {name:20s} @ {offset:3d}: OUT OF BOUNDS (need {end}, have {len(data)})")
            all_match = False
            continue

        pubkey = Pubkey.from_bytes(data[offset:end])
        pubkey_str = str(pubkey)

        expected = EXPECTED_MAINNET.get(name)
        if expected:
            match = "✅" if pubkey_str == expected else "❌ MISMATCH"
        else:
            match = "?"

        print(f"  {match} {name:20s} @ {offset:3d}: {pubkey_str}")

    print()
    print("=" * 70)

    if EXPECTED_MAINNET:
        if all_match:
            print("RESULT: All offsets match expected values. Safe to proceed.")
        else:
            print("RESULT: OFFSET MISMATCH DETECTED. Do NOT run the bot.")
            print("        Update RAYDIUM_AMM_OFFSETS in main_final_v3.py first.")
    else:
        print("RESULT: Verification incomplete.")
        print("        1. Open the Solscan link above.")
        print("        2. Note the AMM Authority, Open Orders, etc.")
        print("        3. Fill EXPECTED_MAINNET in this script.")
        print("        4. Run again to confirm.")

    await client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify Raydium AMM offsets")
    parser.add_argument("pool", nargs="?", default="58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2",
                        help="Raydium pool address")
    parser.add_argument("--rpc", default="https://api.mainnet-beta.solana.com",
                        help="Solana RPC endpoint")
    args = parser.parse_args()

    asyncio.run(verify(args.pool, args.rpc))
