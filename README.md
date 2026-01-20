# Polymarket Strategy Tester

Paper trading bot comparing two strategies on Polymarket's 15-minute BTC Up/Down markets.

## Strategies

| Strategy | Condition | Theory |
|----------|-----------|--------|
| **A (Undervalued)** | Buy when price ≤ $0.48 | Market is mispriced, revert to 50/50 |
| **B (Momentum)** | Buy when price ≥ $0.52 | Smart money knows something |

## How It Works

1. **Entry**: At t+1 market's 20-minute countdown, check prices
2. **Condition**: If price meets strategy threshold, place 10-share limit order
3. **Exit**: Cancel unfilled orders at 15min 30sec mark
4. **Resolution**: Track filled orders to market resolution, calculate P&L

## Quick Start

```bash
# 1. Clone and enter directory
cd polymarket_strategy_tester

# 2. Install dependencies
pip install -e .

# 3. Copy and configure environment
cp .env.example .env

# 4. Run the application
python -m web.api

# 5. Open dashboard
# Navigate to http://localhost:8002/static/dashboard.html
```

## Dashboard

The dashboard shows real-time comparison of both strategies:
- Current market state and prices
- Active paper orders
- Trade history per strategy
- Win rate, P&L, and ROI metrics

## Configuration

Edit `.env` to customize:
- `UNDERVALUED_THRESHOLD`: Price threshold for Strategy A (default: 0.48)
- `MOMENTUM_THRESHOLD`: Price threshold for Strategy B (default: 0.52)
- `ORDER_SIZE_SHARES`: Shares per order (default: 10)
- `ENTRY_COUNTDOWN_SECONDS`: When to check prices (default: 1200 = 20 min)
- `EXIT_COUNTDOWN_SECONDS`: When to cancel (default: 930 = 15m 30s)

## Project Structure

```
polymarket_strategy_tester/
├── src/
│   ├── __init__.py
│   ├── config.py          # Configuration loading
│   ├── models.py          # Data models
│   ├── market_tracker.py  # Market discovery & countdown
│   ├── strategy_engine.py # Strategy logic & paper trading
│   └── clob_client.py     # Polymarket API client
├── web/
│   ├── api.py             # FastAPI backend
│   └── static/
│       ├── dashboard.html
│       └── dashboard.js
├── tests/
├── pyproject.toml
├── .env.example
└── README.md
```

## License

MIT
