"""Kalshi paper-only arbitrage runner (V1)."""

from __future__ import annotations

import os

from trading_bot.common import DecisionAction, MarketSnapshot, OrderBookLevel, utc_now
from trading_bot.config import AppConfig, load_default_config
from trading_bot.data import KalshiDataClient
from trading_bot.decision import DecisionPolicy
from trading_bot.execution import PaperExecutionEngine, SafetyGuard
from trading_bot.monitoring import Reporter
from trading_bot.risk import RiskManager
from trading_bot.signals import ArbitrageDetector


def build_sample_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        ticker="SAMPLE-KALSHI-MARKET",
        yes_ask=OrderBookLevel(price=0.48, size=400.0),
        no_ask=OrderBookLevel(price=0.49, size=400.0),
        last_updated=utc_now(),
        source="sample",
    )


def run_once(
    config: AppConfig | None = None,
    snapshot: MarketSnapshot | None = None,
    ticker: str | None = None,
) -> dict[str, object]:
    cfg = config or load_default_config()
    cfg.validate()

    reporter = Reporter()
    risk_manager = RiskManager(cfg.risk)
    guard = SafetyGuard(cfg, on_critical=reporter.critical)
    guard.assert_paper_only()
    data_client = KalshiDataClient(cfg.kalshi_base_url, guard)

    detector = ArbitrageDetector(
        fee_bps=cfg.execution.fee_bps,
        slippage_bps=cfg.execution.slippage_bps,
        min_net_edge=cfg.execution.min_net_edge,
    )
    policy = DecisionPolicy(cfg, risk_manager)
    engine = PaperExecutionEngine(cfg, risk_manager, reporter)

    if snapshot is not None:
        market_snapshot = snapshot
    elif ticker:
        try:
            market_snapshot = data_client.fetch_market_snapshot(ticker)
        except Exception as exc:  # pragma: no cover - network path is environment-dependent
            reporter.critical(f"Failed to fetch market snapshot for {ticker}: {exc}")
            risk_manager.halt("Market data fetch failed")
            return {
                "decision": DecisionAction.HALT.value,
                "reason": "Market data fetch failed",
                "execution_status": "not_attempted",
                "net_pnl": 0.0,
                "win_rate": 0.0,
                "paused_for_review": False,
                "critical_alerts": reporter.critical_alerts,
                "daily_report": {},
            }
    else:
        market_snapshot = build_sample_snapshot()
    opportunity = detector.detect(market_snapshot)
    decision = policy.evaluate(market_snapshot, opportunity)

    executed_status = "not_attempted"
    if decision.action == DecisionAction.EXECUTE_PAPER and decision.intent and decision.opportunity:
        fill = engine.simulate_arb_pair(decision.intent, decision.opportunity, market_snapshot)
        executed_status = fill.status

    performance = engine.performance()
    red_day_paused = risk_manager.apply_red_day_policy()
    daily_report = reporter.build_daily_report(performance, risk_manager.state)

    return {
        "decision": decision.action.value,
        "reason": decision.reason,
        "execution_status": executed_status,
        "net_pnl": performance.net_pnl,
        "win_rate": performance.win_rate,
        "paused_for_review": red_day_paused,
        "critical_alerts": reporter.critical_alerts,
        "daily_report": daily_report,
    }


def main() -> None:
    ticker = os.getenv("KALSHI_MARKET_TICKER")
    result = run_once(ticker=ticker)
    print("Execution mode: paper-only")
    print(f"Decision: {result['decision']} ({result['reason']})")
    print(f"Execution status: {result['execution_status']}")
    print(f"Net PnL (paper): {result['net_pnl']:.4f}")
    print(f"Win rate (paper): {result['win_rate']:.2%}")
    print(f"Paused for review: {result['paused_for_review']}")


if __name__ == "__main__":
    main()
