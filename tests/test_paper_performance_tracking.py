from trading_bot.common import MarketSnapshot, OrderBookLevel, TradeIntent, utc_now
from trading_bot.config import load_default_config
from trading_bot.execution import PaperExecutionEngine
from trading_bot.learning import ModelMetrics, NightlyRetrainer
from trading_bot.monitoring import Reporter
from trading_bot.risk import RiskManager
from trading_bot.signals import ArbitrageDetector


def test_performance_tracking_and_reporting() -> None:
    config = load_default_config()
    reporter = Reporter()
    risk = RiskManager(config.risk)
    engine = PaperExecutionEngine(config, risk, reporter)

    snapshot = MarketSnapshot(
        ticker="TEST-PERF",
        yes_ask=OrderBookLevel(price=0.48, size=100.0),
        no_ask=OrderBookLevel(price=0.49, size=100.0),
        last_updated=utc_now(),
    )
    detector = ArbitrageDetector(fee_bps=0.0, slippage_bps=0.0)
    opportunity = detector.detect(snapshot)
    assert opportunity is not None

    intent = TradeIntent(
        ticker=snapshot.ticker,
        strategy="arb_yes_no_pair",
        yes_price=opportunity.yes_price,
        no_price=opportunity.no_price,
        shares=10.0,
        notional=10.0 * opportunity.gross_cost_per_share,
    )

    engine.simulate_arb_pair(intent, opportunity, snapshot)
    performance = engine.performance()
    report = reporter.build_daily_report(performance, risk.state)

    assert performance.total_trades == 1
    assert performance.win_rate == 1.0
    assert report["net_pnl"] > 0


def test_negative_day_triggers_pause_for_review() -> None:
    config = load_default_config()
    risk = RiskManager(config.risk)

    risk.record_realized_pnl(-1.0)
    paused = risk.apply_red_day_policy()

    assert paused is True
    assert risk.state.paused_for_review is True
    assert risk.state.halted is True


def test_nightly_retrain_uses_guarded_promotion() -> None:
    retrainer = NightlyRetrainer()
    baseline = ModelMetrics(
        expected_value_per_trade=0.01,
        win_rate=0.55,
        calibration_error=0.02,
        max_drawdown=120.0,
    )
    candidate = ModelMetrics(
        expected_value_per_trade=0.015,
        win_rate=0.58,
        calibration_error=0.02,
        max_drawdown=100.0,
    )

    result = retrainer.evaluate_and_promote(baseline, candidate)
    assert result.promoted is True


def test_remaining_trade_capacity_respects_open_exposure() -> None:
    config = load_default_config()
    risk = RiskManager(config.risk)
    risk.reserve_exposure(450.0)

    remaining = risk.remaining_trade_capacity()
    assert remaining == 50.0
