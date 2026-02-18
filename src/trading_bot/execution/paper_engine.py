from __future__ import annotations

from datetime import date
from typing import List

from trading_bot.common import ArbOpportunity, DailyPerformance, MarketSnapshot, PaperFill, TradeIntent, utc_now
from trading_bot.config import AppConfig
from trading_bot.execution.interfaces import ExecutionEngine
from trading_bot.execution.live_guard import LiveTradeBlockedError
from trading_bot.monitoring.reporter import Reporter
from trading_bot.risk.manager import RiskManager


class PaperExecutionEngine(ExecutionEngine):
    def __init__(self, config: AppConfig, risk_manager: RiskManager, reporter: Reporter) -> None:
        self._config = config
        self._risk_manager = risk_manager
        self._reporter = reporter
        self.ledger: List[PaperFill] = []

    def simulate_arb_pair(
        self,
        intent: TradeIntent,
        opportunity: ArbOpportunity,
        snapshot: MarketSnapshot,
    ) -> PaperFill:
        if intent.shares > opportunity.shares_available:
            self._reporter.record_missed(snapshot.ticker, "Atomic pair fill failed: insufficient two-leg size")
            return PaperFill(
                ticker=snapshot.ticker,
                shares=0.0,
                notional=0.0,
                gross_payout=0.0,
                fees=0.0,
                slippage=0.0,
                net_pnl=0.0,
                filled_at=utc_now(),
                status="skipped_atomic_or_cancel",
            )

        if not self._risk_manager.can_open_notional(intent.notional):
            self._risk_manager.halt("Risk check failed at execution")
            self._reporter.critical("Risk check failed at execution")
            return PaperFill(
                ticker=snapshot.ticker,
                shares=0.0,
                notional=0.0,
                gross_payout=0.0,
                fees=0.0,
                slippage=0.0,
                net_pnl=0.0,
                filled_at=utc_now(),
                status="halted_by_risk",
            )

        self._risk_manager.reserve_exposure(intent.notional)

        fees = intent.notional * (self._config.execution.fee_bps / 10000.0)
        slippage = intent.notional * (self._config.execution.slippage_bps / 10000.0)
        gross_payout = intent.shares
        net_pnl = gross_payout - intent.notional - fees - slippage

        fill = PaperFill(
            ticker=snapshot.ticker,
            shares=intent.shares,
            notional=intent.notional,
            gross_payout=gross_payout,
            fees=fees,
            slippage=slippage,
            net_pnl=net_pnl,
            filled_at=utc_now(),
            status="filled",
        )

        self.ledger.append(fill)
        self._reporter.record_trade(fill)
        self._risk_manager.release_exposure(intent.notional)
        self._risk_manager.record_realized_pnl(net_pnl)
        return fill

    def place_live_order(self, order: object) -> None:
        self._reporter.critical("Live order attempt blocked in paper mode")
        raise LiveTradeBlockedError("Live order attempt blocked in paper mode")

    def performance(self) -> DailyPerformance:
        filled = [trade for trade in self.ledger if trade.status == "filled"]
        wins = sum(1 for trade in filled if trade.net_pnl > 0)
        losses = sum(1 for trade in filled if trade.net_pnl < 0)
        total = len(filled)
        win_rate = float(wins / total) if total else 0.0
        net_pnl = sum(trade.net_pnl for trade in filled)
        return DailyPerformance(
            date=date.today().isoformat(),
            total_trades=total,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            net_pnl=net_pnl,
            missed_opportunities=len(self._reporter.missed_records),
            paused_for_review=self._risk_manager.state.paused_for_review,
        )
