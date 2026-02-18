import pytest

from trading_bot.common import ExecutionMode
from trading_bot.config import load_default_config
from trading_bot.execution import LiveTradeBlockedError, PaperExecutionEngine, SafetyGuard
from trading_bot.monitoring import Reporter
from trading_bot.risk import RiskManager


def test_v1_rejects_live_mode() -> None:
    config = load_default_config()
    config.execution.mode = ExecutionMode.LIVE
    with pytest.raises(ValueError):
        config.validate()


def test_config_rejects_exposure_above_starting_capital() -> None:
    config = load_default_config()
    config.risk.max_total_exposure = 6000.0
    with pytest.raises(ValueError):
        config.validate()


def test_config_rejects_candidate_pool_smaller_than_scan_limit() -> None:
    config = load_default_config()
    config.execution.market_scan_limit = 200
    config.execution.market_candidate_pool_limit = 199
    with pytest.raises(ValueError):
        config.validate()


def test_config_rejects_min_trade_above_max_trade() -> None:
    config = load_default_config()
    config.risk.min_dollars_per_trade = 101.0
    config.risk.max_dollars_per_trade = 100.0
    with pytest.raises(ValueError):
        config.validate()


def test_config_rejects_invalid_degraded_cycle_limit() -> None:
    config = load_default_config()
    config.execution.max_consecutive_degraded_cycles = 0
    with pytest.raises(ValueError):
        config.validate()


def test_config_rejects_invalid_snapshot_failure_limit() -> None:
    config = load_default_config()
    config.execution.max_snapshot_fetch_failures_per_cycle = 0
    with pytest.raises(ValueError):
        config.validate()


def test_config_rejects_invalid_http_hard_timeout() -> None:
    config = load_default_config()
    config.execution.http_hard_timeout_seconds = 0
    with pytest.raises(ValueError):
        config.validate()


def test_safety_guard_blocks_non_data_paths() -> None:
    config = load_default_config()
    reporter = Reporter()
    guard = SafetyGuard(config, on_critical=reporter.critical)

    with pytest.raises(LiveTradeBlockedError):
        guard.block_live_endpoint("https://api.kalshi.com/trade-api/v2/orders", method="GET")

    assert reporter.critical_alerts


def test_paper_engine_blocks_live_order_calls() -> None:
    config = load_default_config()
    reporter = Reporter()
    risk = RiskManager(config.risk)
    engine = PaperExecutionEngine(config, risk, reporter)

    with pytest.raises(LiveTradeBlockedError):
        engine.place_live_order({"ticker": "TEST"})

    assert any("blocked" in message.lower() for message in reporter.critical_alerts)
