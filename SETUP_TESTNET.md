# Virtual Trading Environment (Binance Testnet)

Use these commands in terminal:

```bash
cd /Users/hussain/RASIM_FIN_2
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set testnet API keys:

```bash
export BINANCE_TESTNET_API_KEY="your_testnet_key"
export BINANCE_TESTNET_API_SECRET="your_testnet_secret"
```

Connectivity test only:

```bash
python binance_testnet.py --symbol BTC/USDT:USDT
```

Place tiny testnet order:

```bash
python binance_testnet.py --symbol BTC/USDT:USDT --side BUY --amount 0.001 --place-order
```

Execute a strategy decision JSON on testnet:

```bash
cat > decision.json <<'EOF'
{
  "action": "BUY",
  "reason": "manual sandbox test",
  "entry_price": 65000,
  "quantity": 0.01
}
EOF

python binance_testnet.py --symbol BTC/USDT:USDT --decision-json decision.json
```

Run data pipeline + backtest:

```bash
python -m data_pipeline.main \
  --symbol BTC/USDT \
  --start-date 2024-01-01 \
  --end-date 2024-01-05 \
  --output-dir ./data_pipeline/data \
  --capital 10000 \
  --key-levels "42000,43000"
```

Live strategy -> testnet execution loop:

```bash
python live_testnet_runner.py \
  --symbol BTC/USDT:USDT \
  --capital 10000 \
  --key-levels "42000,43000" \
  --loop-seconds 60
```

By default, orders are sent as `test` validation requests (`params.test=true`) so they validate payloads without live fills. Add `--live-order` only if you intentionally want real fills on your connected account.
