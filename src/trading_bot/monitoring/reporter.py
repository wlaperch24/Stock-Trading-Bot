from __future__ import annotations

from typing import Any, Dict, List

from trading_bot.common import DailyPerformance, PaperFill, RiskState


class Reporter:
    def __init__(self) -> None:
        self.critical_alerts: List[str] = []
        self.trade_records: List[PaperFill] = []
        self.missed_records: List[Dict[str, Any]] = []
        self.daily_reports: List[Dict[str, Any]] = []

    def critical(self, message: str) -> None:
        self.critical_alerts.append(message)

    def record_trade(self, fill: PaperFill) -> None:
        self.trade_records.append(fill)

    def record_missed(self, ticker: str, reason: str) -> None:
        self.missed_records.append({"ticker": ticker, "reason": reason})

    def build_daily_report(self, performance: DailyPerformance, risk_state: RiskState) -> Dict[str, Any]:
        report = {
            "date": performance.date,
            "total_trades": performance.total_trades,
            "wins": performance.wins,
            "losses": performance.losses,
            "win_rate": performance.win_rate,
            "net_pnl": performance.net_pnl,
            "missed_opportunities": performance.missed_opportunities,
            "paused_for_review": risk_state.paused_for_review,
            "halt_reason": risk_state.halt_reason,
        }
        self.daily_reports.append(report)
        return report
