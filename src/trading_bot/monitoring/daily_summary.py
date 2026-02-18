from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

from trading_bot.common import utc_now


def _rows_for_date(path: Path, target_date: str) -> list[dict[str, str]]:
    if not path.exists():
        return []

    rows: list[dict[str, str]] = []
    with path.open("r", newline="", encoding="utf-8") as file_obj:
        reader = csv.DictReader(file_obj)
        for row in reader:
            timestamp = str(row.get("timestamp", ""))
            if timestamp[:10] == target_date:
                rows.append({key: str(value) for key, value in row.items()})
    return rows


def build_daily_summary(ledger_dir: str, target_date: str | None = None) -> dict[str, Any]:
    date = target_date or utc_now().date().isoformat()

    base = Path(ledger_dir)
    decision_file = base / "decision_log.csv"
    trade_file = base / "trade_log.csv"

    decision_rows = _rows_for_date(decision_file, date)
    trade_rows = _rows_for_date(trade_file, date)

    trades_executed = 0
    total_paper_pnl = 0.0
    total_executed_notional = 0.0
    profitable_trades = 0
    losing_trades = 0
    breakeven_trades = 0
    traded_markets: dict[str, dict[str, float]] = {}
    trade_details: list[dict[str, Any]] = []
    for row in trade_rows:
        if row.get("status") != "filled":
            continue
        trades_executed += 1
        try:
            net_pnl = float(row.get("net_pnl", 0.0))
            notional = float(row.get("notional", 0.0))
        except (TypeError, ValueError):
            continue
        total_paper_pnl += net_pnl
        total_executed_notional += notional

        if net_pnl > 0:
            profitable_trades += 1
        elif net_pnl < 0:
            losing_trades += 1
        else:
            breakeven_trades += 1

        ticker = row.get("ticker", "UNKNOWN")
        market_stats = traded_markets.setdefault(
            ticker,
            {"trades": 0.0, "notional": 0.0, "net_pnl": 0.0},
        )
        market_stats["trades"] += 1.0
        market_stats["notional"] += notional
        market_stats["net_pnl"] += net_pnl

        return_pct = ((net_pnl / notional) * 100.0) if notional > 0 else 0.0
        trade_details.append(
            {
                "timestamp": row.get("timestamp", ""),
                "ticker": ticker,
                "notional": round(notional, 6),
                "net_pnl": round(net_pnl, 6),
                "return_pct": round(return_pct, 6),
                "held_seconds": row.get("held_seconds", "0"),
                "opened_at": row.get("opened_at", ""),
                "closed_at": row.get("closed_at", ""),
            }
        )

    avg_pnl_per_trade = (total_paper_pnl / trades_executed) if trades_executed else 0.0
    avg_return_per_trade_pct = (
        ((total_paper_pnl / total_executed_notional) * 100.0) if total_executed_notional > 0 else 0.0
    )

    skip_reason_counter = Counter(
        row.get("reason", "unknown")
        for row in decision_rows
        if row.get("decision") == "skip"
    )

    per_market: dict[str, dict[str, float]] = {}
    for row in decision_rows:
        ticker = row.get("ticker", "")
        if not ticker:
            continue

        stats = per_market.setdefault(
            ticker,
            {"observations": 0.0, "arb_hits": 0.0, "executed_trades": 0.0},
        )
        stats["observations"] += 1.0

        if row.get("had_opportunity", "").lower() == "true":
            stats["arb_hits"] += 1.0
        if row.get("executed_status") == "filled":
            stats["executed_trades"] += 1.0

    top_markets = []
    for ticker, stats in per_market.items():
        observations = int(stats["observations"])
        arb_hits = int(stats["arb_hits"])
        executed = int(stats["executed_trades"])
        hit_rate = float(arb_hits / observations) if observations else 0.0
        top_markets.append(
            {
                "ticker": ticker,
                "observations": observations,
                "arb_hits": arb_hits,
                "arb_hit_rate": round(hit_rate, 4),
                "executed_trades": executed,
            }
        )

    top_markets.sort(
        key=lambda row: (
            row["arb_hit_rate"],
            row["arb_hits"],
            row["observations"],
        ),
        reverse=True,
    )

    traded_markets_summary = []
    for ticker, stats in traded_markets.items():
        trades = int(stats["trades"])
        notional = float(stats["notional"])
        net_pnl = float(stats["net_pnl"])
        avg_pnl = (net_pnl / trades) if trades else 0.0
        return_pct = ((net_pnl / notional) * 100.0) if notional > 0 else 0.0
        traded_markets_summary.append(
            {
                "ticker": ticker,
                "trades": trades,
                "notional": round(notional, 6),
                "net_pnl": round(net_pnl, 6),
                "avg_pnl_per_trade": round(avg_pnl, 6),
                "return_pct": round(return_pct, 6),
            }
        )
    traded_markets_summary.sort(key=lambda row: (row["net_pnl"], row["trades"]), reverse=True)
    trade_details.sort(key=lambda row: str(row["timestamp"]))

    return {
        "date": date,
        "trades_executed": trades_executed,
        "total_paper_pnl": round(total_paper_pnl, 6),
        "total_executed_notional": round(total_executed_notional, 6),
        "avg_pnl_per_trade": round(avg_pnl_per_trade, 6),
        "avg_return_per_trade_pct": round(avg_return_per_trade_pct, 6),
        "profitable_trades": profitable_trades,
        "losing_trades": losing_trades,
        "breakeven_trades": breakeven_trades,
        "skip_reasons": dict(skip_reason_counter.most_common()),
        "traded_markets": traded_markets_summary,
        "trade_details": trade_details,
        "top_markets_by_arb_hit_rate": top_markets[:10],
        "decision_rows": len(decision_rows),
        "trade_rows": len(trade_rows),
        "decision_log_path": str(decision_file),
        "trade_log_path": str(trade_file),
    }
