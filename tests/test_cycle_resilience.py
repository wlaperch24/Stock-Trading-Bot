from pathlib import Path

from trading_bot.common import MarketDescriptor, MarketSnapshot, OrderBookLevel, utc_now
from trading_bot.config import load_default_config
from trading_bot.main import _build_runtime, _build_selector, run_market_scan_cycle


def _snapshot_for(ticker: str) -> MarketSnapshot:
    return MarketSnapshot(
        ticker=ticker,
        yes_ask=OrderBookLevel(price=0.48, size=300.0),
        no_ask=OrderBookLevel(price=0.49, size=300.0),
        last_updated=utc_now(),
    )


def _config(tmp_path: Path):
    cfg = load_default_config()
    cfg.execution.market_scan_limit = 2
    cfg.execution.market_candidate_pool_limit = 2
    cfg.execution.exploration_markets_per_cycle = 0
    cfg.execution.min_market_liquidity = 0.0
    cfg.execution.ledger_dir = str(tmp_path / "ledger")
    cfg.execution.selector_state_file = str(tmp_path / "selector_state.json")
    cfg.execution.market_cache_file = str(tmp_path / "market_cache.json")
    cfg.validate()
    return cfg


def test_shared_runtime_keeps_learning_and_pnl_across_cycles(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    runtime = _build_runtime(cfg)
    selector = _build_selector(cfg)

    markets = [MarketDescriptor("MKT-1", liquidity_score=100), MarketDescriptor("MKT-2", liquidity_score=90)]
    runtime.data_client.discover_open_markets = lambda **_: markets  # type: ignore[assignment]
    runtime.data_client.fetch_market_snapshot = lambda ticker: _snapshot_for(ticker)  # type: ignore[assignment]

    first = run_market_scan_cycle(config=cfg, selector=selector, runtime=runtime)
    second = run_market_scan_cycle(config=cfg, selector=selector, runtime=runtime)

    assert first["cycle_status"] == "ok"
    assert second["cycle_status"] == "ok"
    assert second["net_pnl"] > first["net_pnl"]


def test_cycle_uses_cached_markets_when_discovery_fails(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    runtime = _build_runtime(cfg)
    selector = _build_selector(cfg)

    markets = [MarketDescriptor("MKT-1", liquidity_score=100)]
    runtime.data_client.discover_open_markets = lambda **_: markets  # type: ignore[assignment]
    runtime.data_client.fetch_market_snapshot = lambda ticker: _snapshot_for(ticker)  # type: ignore[assignment]

    first = run_market_scan_cycle(config=cfg, selector=selector, runtime=runtime)
    assert first["used_cached_candidates"] is False

    def _raise_discovery(**_):
        raise RuntimeError("network down")

    runtime.data_client.discover_open_markets = _raise_discovery  # type: ignore[assignment]
    second = run_market_scan_cycle(config=cfg, selector=selector, runtime=runtime)

    assert second["cycle_status"] == "ok"
    assert second["used_cached_candidates"] is True
    assert second["selected_markets"] >= 1
