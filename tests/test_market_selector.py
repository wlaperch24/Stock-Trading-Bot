from trading_bot.common import MarketDescriptor
from trading_bot.signals import AdaptiveMarketSelector


def _markets(count: int) -> list[MarketDescriptor]:
    return [MarketDescriptor(ticker=f"MKT-{i}", liquidity_score=1000 - i) for i in range(count)]


def test_selector_returns_scan_limit() -> None:
    selector = AdaptiveMarketSelector(scan_limit=5, min_observations=4, exploration_size=2)
    selected = selector.select_market_batch(_markets(12))
    assert len(selected) == 5


def test_selector_requires_multiple_observations_before_deprioritizing() -> None:
    selector = AdaptiveMarketSelector(scan_limit=3, min_observations=5, exploration_size=1)
    base_markets = _markets(6)

    for _ in range(4):
        selector.observe_market("MKT-0", had_arbitrage=False)

    selected = selector.select_market_batch(base_markets)
    tickers = {market.ticker for market in selected}
    assert "MKT-0" in tickers



def test_selector_prioritizes_consistent_arb_markets() -> None:
    selector = AdaptiveMarketSelector(scan_limit=3, min_observations=3, exploration_size=0)
    markets = _markets(6)

    for _ in range(6):
        selector.observe_market("MKT-1", had_arbitrage=True, edge_per_share=0.02)
        selector.record_trade_result("MKT-1", profitable=True)

    for _ in range(6):
        selector.observe_market("MKT-2", had_arbitrage=False)

    selected = selector.select_market_batch(markets)
    tickers = [market.ticker for market in selected]

    assert "MKT-1" in tickers
    assert "MKT-2" not in tickers


def test_selector_state_persists_between_instances(tmp_path) -> None:
    state_path = tmp_path / "selector_state.json"

    selector = AdaptiveMarketSelector(scan_limit=3, min_observations=3, exploration_size=0)
    for _ in range(5):
        selector.observe_market("MKT-1", had_arbitrage=True, edge_per_share=0.02)
        selector.record_trade_result("MKT-1", profitable=True)
    selector.save_state(str(state_path))

    restored = AdaptiveMarketSelector(scan_limit=3, min_observations=3, exploration_size=0)
    loaded = restored.load_state(str(state_path))
    assert loaded is True

    stats = restored.snapshot_stats(top_n=1)
    assert stats[0]["ticker"] == "MKT-1"
    assert stats[0]["arb_hits"] == 5
