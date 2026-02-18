# Kalshi Paper-Only Trading Agent (V1)

This project is a paper-trading framework that reads real-time Kalshi market data and simulates arbitrage trades.

## Safety Guarantees
- Default execution mode is `paper`.
- V1 runtime rejects `live` mode.
- Non-GET requests are blocked in paper mode.
- Trade/order/portfolio API paths are blocked in paper mode.
- Paper ledger is the only source of trade PnL and success tracking.

## Current V1 Scope
- Venue: Kalshi (market data only in runtime)
- Strategy: Arbitrage-first complementary YES/NO pair detection
- Risk limits:
  - Starting capital: `$5,000`
  - Max trade notional: `$100`
  - Max total exposure: `$500`
  - Daily loss stop: `$300`
- Red-day policy: automatic pause + review required
- Learning policy: nightly retrain with guarded promotion checks

## Project Layout
- `src/trading_bot/config.py` - runtime config and safety defaults
- `src/trading_bot/common/types.py` - core enums/dataclasses
- `src/trading_bot/data/kalshi_client.py` - read-only Kalshi client
- `src/trading_bot/signals/arb_detector.py` - deterministic arb detection
- `src/trading_bot/decision/policy.py` - trade gating logic
- `src/trading_bot/execution/live_guard.py` - paper-lock endpoint guard
- `src/trading_bot/execution/paper_engine.py` - paper fills + ledger
- `src/trading_bot/risk/manager.py` - risk controls and pause policy
- `src/trading_bot/learning/retrainer.py` - nightly model promotion guardrails
- `src/trading_bot/monitoring/reporter.py` - alerts and daily reporting
- `src/trading_bot/main.py` - runnable orchestration entrypoint

## Run Locally
```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 src/trading_bot/main.py
```

Use real-time Kalshi production market data (still paper execution only):
```bash
KALSHI_MARKET_TICKER=YOUR_MARKET_TICKER PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 src/trading_bot/main.py
```

## Test Files
- `tests/test_paper_lock.py`
- `tests/test_arb_pairing.py`
- `tests/test_paper_performance_tracking.py`

Note: `pytest` is required to run tests and is not installed in the current environment.
