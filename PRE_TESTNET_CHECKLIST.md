# Pre-Testnet Checklist

## 1. Raydium Offset Verification (BLOCKER)
```bash
pip install solana solders
python verify_raydium_offsets.py 58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2
```
- [ ] Buka https://solscan.io/account/58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2
- [ ] Bandingkan pubkey di setiap offset dengan output script
- [ ] Jika cocok → lanjut. Jika tidak → edit `RAYDIUM_AMM_OFFSETS` di `main_final_v3.py`

## 2. Environment Variables
Buat file `.env`:
```
SOLANA_PRIVATE_KEY=your_base58_key_here
EVM_PRIVATE_KEY=0x_your_64_hex_chars_here
SOLANA_RPC_URL=https://api.devnet.solana.com
SOLANA_WS_URL=wss://api.devnet.solana.com
EVM_RPC_URL=https://eth-sepolia.g.alchemy.com/v2/YOUR_KEY
EVM_WS_URL=wss://eth-sepolia.g.alchemy.com/v2/YOUR_KEY
POOL_B_EVM=0x_address_of_second_pool
EXECUTOR_CONTRACT=0x_your_deployed_contract
JITO_BUNDLE_URL=https://mainnet.block-engine.jito.wtf/api/v1/bundles
DEX_ROUTERS=0x7a250d5630b4cf539739df2c5dacb4c659f2488d
```

## 3. Smart Contract Deployment (EVM)
- [ ] Deploy `executeArbitrage` contract ke Sepolia
- [ ] Isi `EXECUTOR_CONTRACT` dengan address hasil deploy
- [ ] Verifikasi contract ABI cocok dengan kode bot

## 4. Testnet Run (Dry-Run Mode)
```bash
pip install web3 solders solana structlog aiohttp websockets python-dotenv uvloop
python main_final_v3.py
```
- [ ] Bot starts without crash
- [ ] WebSocket listeners connect
- [ ] State hydration completes
- [ ] Opportunities detected (but may not execute if profit < threshold)
- [ ] Health check responds at http://localhost:8080/health

## 5. Before Mainnet
- [ ] Switch RPC dari devnet/testnet ke mainnet
- [ ] Naikkan `MIN_PROFIT_USD` ke nilai yang realistis (≥ $50)
- [ ] Verifikasi `FLASHBOTS_RELAY_URL` untuk mainnet
- [ ] Pastikan saldo SOL/ETH cukup untuk gas + tips
- [ ] Jalankan dengan `MAX_CONCURRENT_EXECUTIONS=1` dulu untuk safety
