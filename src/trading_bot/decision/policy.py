from __future__ import annotations

from datetime import timedelta

from trading_bot.common import ArbOpportunity, DecisionAction, DecisionResult, MarketSnapshot, TradeIntent, utc_now
from trading_bot.config import AppConfig
from trading_bot.risk.manager import RiskManager


class DecisionPolicy:
    def __init__(self, config: AppConfig, risk_manager: RiskManager, max_staleness_seconds: int = 45) -> None:
        self._config = config
        self._risk_manager = risk_manager
        self._max_staleness = timedelta(seconds=max_staleness_seconds)

    def evaluate(self, snapshot: MarketSnapshot, opportunity: ArbOpportunity | None) -> DecisionResult:
        if self._risk_manager.state.halted:
            return DecisionResult(action=DecisionAction.HALT, reason="Risk manager halted trading")

        if utc_now() - snapshot.last_updated > self._max_staleness:
            self._risk_manager.halt("Stale market snapshot")
            return DecisionResult(action=DecisionAction.HALT, reason="Stale market snapshot")

        if opportunity is None:
            return DecisionResult(action=DecisionAction.SKIP, reason="No deterministic arbitrage found")

        if opportunity.expires_at <= utc_now():
            return DecisionResult(action=DecisionAction.SKIP, reason="Opportunity expired")

        if opportunity.net_edge_per_share <= self._config.execution.min_net_edge:
            return DecisionResult(action=DecisionAction.SKIP, reason="Net edge below threshold")

        pair_cost = opportunity.gross_cost_per_share
        if pair_cost <= 0:
            return DecisionResult(action=DecisionAction.SKIP, reason="Invalid pair cost")

        target_notional = self._config.risk.min_dollars_per_trade
        if target_notional > self._config.risk.max_dollars_per_trade:
            return DecisionResult(action=DecisionAction.HALT, reason="Invalid fixed trade size configuration")

        remaining_capacity = self._risk_manager.remaining_trade_capacity()
        if remaining_capacity < target_notional:
            return DecisionResult(action=DecisionAction.SKIP, reason="Insufficient remaining risk capacity for fixed trade size")

        max_fillable_notional = opportunity.shares_available * pair_cost
        if max_fillable_notional < target_notional:
            return DecisionResult(action=DecisionAction.SKIP, reason="Insufficient two-leg liquidity for fixed trade size")

        shares = target_notional / pair_cost
        if shares <= 0:
            return DecisionResult(action=DecisionAction.SKIP, reason="Invalid share size for fixed trade size")

        if not self._risk_manager.can_open_notional(target_notional):
            return DecisionResult(action=DecisionAction.SKIP, reason="Risk constraint prevented fixed-size trade")

        return DecisionResult(
            action=DecisionAction.EXECUTE_PAPER,
            reason="Deterministic arbitrage qualifies",
            intent=TradeIntent(
                ticker=opportunity.ticker,
                strategy="arb_yes_no_pair",
                yes_price=opportunity.yes_price,
                no_price=opportunity.no_price,
                shares=shares,
                notional=target_notional,
            ),
            opportunity=opportunity,
        )
