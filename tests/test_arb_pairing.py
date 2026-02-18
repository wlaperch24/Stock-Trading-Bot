from trading_bot.common import MarketSnapshot, OrderBookLevel, TradeIntent, utc_now
from trading_bot.config import load_default_config
from trading_bot.decision import DecisionPolicy
from trading_bot.execution import PaperExecutionEngine
from trading_bot.monitoring import Reporter
from trading_bot.risk import RiskManager
from trading_bot.signals import ArbitrageDetector


def test_arb_detector_finds_positive_edge() -> None:
    snapshot = MarketSnapshot(
        ticker="TEST-ARB",
        yes_ask=OrderBookLevel(price=0.48, size=500.0),
        no_ask=OrderBookLevel(price=0.49, size=500.0),
        last_updated=utc_now(),
    )
    detector = ArbitrageDetector(fee_bps=0.0, slippage_bps=0.0)
    opportunity = detector.detect(snapshot)

    assert opportunity is not None
    assert opportunity.net_edge_per_share > 0


def test_atomic_pair_skips_if_both_legs_unavailable() -> None:
    config = load_default_config()
    reporter = Reporter()
    risk = RiskManager(config.risk)
    engine = PaperExecutionEngine(config, risk, reporter)

    snapshot = MarketSnapshot(
        ticker="TEST-PAIR",
        yes_ask=OrderBookLevel(price=0.48, size=5.0),
        no_ask=OrderBookLevel(price=0.49, size=5.0),
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
        shares=20.0,
        notional=20.0 * opportunity.gross_cost_per_share,
    )

    fill = engine.simulate_arb_pair(intent, opportunity, snapshot)
    assert fill.status == "skipped_atomic_or_cancel"


def test_atomic_pair_fills_when_both_legs_available() -> None:
    config = load_default_config()
    reporter = Reporter()
    risk = RiskManager(config.risk)
    engine = PaperExecutionEngine(config, risk, reporter)

    snapshot = MarketSnapshot(
        ticker="TEST-FILL",
        yes_ask=OrderBookLevel(price=0.47, size=100.0),
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

    fill = engine.simulate_arb_pair(intent, opportunity, snapshot)
    assert fill.status == "filled"
    assert fill.net_pnl > 0


def test_policy_enforces_fixed_100_dollar_trade_size() -> None:
    config = load_default_config()
    risk = RiskManager(config.risk)
    policy = DecisionPolicy(config, risk)
    detector = ArbitrageDetector(fee_bps=0.0, slippage_bps=0.0)

    snapshot = MarketSnapshot(
        ticker="TEST-FIXED-SIZE",
        yes_ask=OrderBookLevel(price=0.47, size=1000.0),
        no_ask=OrderBookLevel(price=0.49, size=1000.0),
        last_updated=utc_now(),
    )
    opportunity = detector.detect(snapshot)
    assert opportunity is not None

    decision = policy.evaluate(snapshot, opportunity)
    assert decision.action.value == "execute_paper"
    assert decision.intent is not None
    assert decision.intent.notional == 100.0


def test_policy_skips_when_liquidity_cannot_fill_fixed_trade_size() -> None:
    config = load_default_config()
    risk = RiskManager(config.risk)
    policy = DecisionPolicy(config, risk)
    detector = ArbitrageDetector(fee_bps=0.0, slippage_bps=0.0)

    # Max fillable notional is 5 * (0.47 + 0.49) = 4.8, below fixed $100 target.
    snapshot = MarketSnapshot(
        ticker="TEST-FIXED-SIZE-SKIP",
        yes_ask=OrderBookLevel(price=0.47, size=5.0),
        no_ask=OrderBookLevel(price=0.49, size=5.0),
        last_updated=utc_now(),
    )
    opportunity = detector.detect(snapshot)
    assert opportunity is not None

    decision = policy.evaluate(snapshot, opportunity)
    assert decision.action.value == "skip"
    assert "fixed trade size" in decision.reason.lower()
