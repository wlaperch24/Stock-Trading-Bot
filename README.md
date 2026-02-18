# Kalshi Paper-Only Trading Agent (V1)

This project is a paper-trading framework that reads real-time Kalshi market data and simulates arbitrage trades.

## Safety Guarantees
- Default execution mode is `paper`.
- V1 runtime rejects `live` mode.
- Non-GET requests are blocked in paper mode.
- Trade/order/portfolio API paths are blocked in paper mode.
- Paper ledger is the only source of trade PnL and success tracking.
- No forced trading: when no qualifying opportunity exists, the bot records `skip` and places no trade.

## Current V1 Scope
- Venue: Kalshi (market data only in runtime)
- Strategy: Arbitrage-first complementary YES/NO pair detection
- Discovery: dynamic market discovery each cycle
- Default scan cadence: every 10 minutes
- Default scan size: up to 200 markets per cycle
- Adaptive selector: revisits historically strong arbitrage markets more often and deprioritizes weak markets only after multiple observations
- Selector learning state persists across restarts (`market_selector_state.json`)
- Candidate market universe cache is used if discovery temporarily fails
- HTTP retries are enabled for transient API/network errors
- Kalshi HTTP client uses hard request timeouts and bypasses system proxy auto-detection for deterministic connectivity behavior
- Continuous mode treats discovery outages as degraded cycles and auto-retries with bounded consecutive-failure protection
- Continuous mode now performs a strict Kalshi connectivity preflight and exits fast with explicit DNS/network diagnostics when data cannot be reached
- Risk limits:
  - Starting capital: `$5,000`
  - Fixed trade notional per executed trade: `$100`
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
- `src/trading_bot/monitoring/ledger_store.py` - CSV decision/trade ledger
- `src/trading_bot/main.py` - runnable orchestration entrypoint

## Run Locally
```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 src/trading_bot/main.py
```

Use one specific market ticker (real-time Kalshi production data, still paper execution only):
```bash
KALSHI_MARKET_TICKER=YOUR_MARKET_TICKER PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 src/trading_bot/main.py
```

Run continuous adaptive scanning (defaults: 200 markets every 10 minutes):
```bash
KALSHI_CONTINUOUS=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 src/trading_bot/main.py
```

Run continuous mode for a fixed number of cycles:
```bash
KALSHI_CONTINUOUS=1 KALSHI_MAX_CYCLES=3 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 src/trading_bot/main.py
```

Run continuous mode for a fixed wall-clock runtime (6 hours):
```bash
KALSHI_CONTINUOUS=1 KALSHI_MAX_RUNTIME_SECONDS=21600 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 src/trading_bot/main.py
```

Print a daily summary (trades executed, total PnL, skip reasons, top markets by arb hit rate):
```bash
KALSHI_DAILY_SUMMARY=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 src/trading_bot/main.py
```

Print summary for a specific date (UTC):
```bash
KALSHI_DAILY_SUMMARY=1 KALSHI_SUMMARY_DATE=2026-02-18 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 src/trading_bot/main.py
```

Export a color-coded Excel file (green profit rows, red loss rows, grand net total):
```bash
KALSHI_EXPORT_EXCEL=1 KALSHI_SUMMARY_DATE=2026-02-18 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 src/trading_bot/main.py
```

Export to a custom file path:
```bash
KALSHI_EXPORT_EXCEL=1 KALSHI_SUMMARY_DATE=2026-02-18 KALSHI_EXCEL_PATH=reports/my_trade_report.xlsx PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 src/trading_bot/main.py
```

Ledger output files (created automatically):
- `data/ledger/decision_log.csv` - every market decision and reason (`execute_paper`, `skip`, `halt`)
- `data/ledger/trade_log.csv` - every executed paper trade with entry/exit timestamps and `held_seconds`
- `data/ledger/market_selector_state.json` - persisted adaptive scan learning state
- `data/ledger/market_candidates_cache.json` - cached market universe for outage fallback

## Test Files
- `tests/test_paper_lock.py`
- `tests/test_arb_pairing.py`
- `tests/test_paper_performance_tracking.py`
- `tests/test_kalshi_client.py`
- `tests/test_market_selector.py`
- `tests/test_ledger_transparency.py`
- `tests/test_kalshi_retry.py`
- `tests/test_cycle_resilience.py`
- `tests/test_run_continuous.py`
- `tests/test_daily_summary.py`
- `tests/test_excel_export.py`

Daily summary now includes:
- total executed notional
- average PnL per executed trade
- average return percentage per executed trade
