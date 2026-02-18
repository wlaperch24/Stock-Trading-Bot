from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from trading_bot.common import ArbOpportunity, DecisionAction, MarketSnapshot, PaperFill, TradeIntent, utc_now


class CsvLedgerStore:
    """CSV-backed paper-trading ledger for transparent review and auditability."""

    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

        self.decision_file = self._base_dir / "decision_log.csv"
        self.trade_file = self._base_dir / "trade_log.csv"

        self._ensure_headers()

    def _ensure_headers(self) -> None:
        if not self.decision_file.exists():
            self._write_header(
                self.decision_file,
                [
                    "timestamp",
                    "cycle_id",
                    "ticker",
                    "decision",
                    "reason",
                    "yes_ask",
                    "no_ask",
                    "had_opportunity",
                    "net_edge_per_share",
                    "executed_status",
                ],
            )

        if not self.trade_file.exists():
            self._write_header(
                self.trade_file,
                [
                    "timestamp",
                    "cycle_id",
                    "ticker",
                    "strategy",
                    "yes_price",
                    "no_price",
                    "shares",
                    "notional",
                    "fees",
                    "slippage",
                    "net_pnl",
                    "status",
                    "opened_at",
                    "closed_at",
                    "held_seconds",
                    "hold_note",
                ],
            )

    @staticmethod
    def _write_header(path: Path, header: list[str]) -> None:
        with path.open("w", newline="", encoding="utf-8") as file_obj:
            writer = csv.writer(file_obj)
            writer.writerow(header)

    def append_decision(
        self,
        cycle_id: str,
        snapshot: MarketSnapshot,
        decision: DecisionAction,
        reason: str,
        opportunity: Optional[ArbOpportunity],
        executed_status: str,
    ) -> None:
        with self.decision_file.open("a", newline="", encoding="utf-8") as file_obj:
            writer = csv.writer(file_obj)
            writer.writerow(
                [
                    utc_now().isoformat(),
                    cycle_id,
                    snapshot.ticker,
                    decision.value,
                    reason,
                    f"{snapshot.yes_ask.price:.6f}",
                    f"{snapshot.no_ask.price:.6f}",
                    str(opportunity is not None).lower(),
                    f"{(opportunity.net_edge_per_share if opportunity else 0.0):.8f}",
                    executed_status,
                ]
            )

    def append_trade(
        self,
        cycle_id: str,
        intent: TradeIntent,
        fill: PaperFill,
    ) -> None:
        opened_at = fill.filled_at
        closed_at = fill.filled_at
        held_seconds = 0.0

        with self.trade_file.open("a", newline="", encoding="utf-8") as file_obj:
            writer = csv.writer(file_obj)
            writer.writerow(
                [
                    utc_now().isoformat(),
                    cycle_id,
                    fill.ticker,
                    intent.strategy,
                    f"{intent.yes_price:.6f}",
                    f"{intent.no_price:.6f}",
                    f"{fill.shares:.6f}",
                    f"{fill.notional:.6f}",
                    f"{fill.fees:.6f}",
                    f"{fill.slippage:.6f}",
                    f"{fill.net_pnl:.6f}",
                    fill.status,
                    opened_at.isoformat(),
                    closed_at.isoformat(),
                    f"{held_seconds:.3f}",
                    "Instant settlement assumption for deterministic pair simulation",
                ]
            )
