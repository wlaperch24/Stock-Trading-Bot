from trading_bot.monitoring import build_daily_summary


def test_build_daily_summary_aggregates_metrics(tmp_path) -> None:
    base = tmp_path / "ledger"
    base.mkdir(parents=True, exist_ok=True)

    decision_csv = base / "decision_log.csv"
    trade_csv = base / "trade_log.csv"

    decision_csv.write_text(
        "timestamp,cycle_id,ticker,decision,reason,yes_ask,no_ask,had_opportunity,net_edge_per_share,executed_status\n"
        "2026-02-18T01:00:00+00:00,C1,MKT-A,skip,No deterministic arbitrage found,0.6,0.5,false,0.0,skipped\n"
        "2026-02-18T01:01:00+00:00,C1,MKT-B,execute_paper,Deterministic arbitrage qualifies,0.48,0.49,true,0.02,filled\n"
        "2026-02-18T01:02:00+00:00,C1,MKT-B,skip,No deterministic arbitrage found,0.6,0.5,false,0.0,skipped\n"
        "2026-02-18T01:03:00+00:00,C1,MKT-C,execute_paper,Deterministic arbitrage qualifies,0.40,0.55,true,0.03,filled\n",
        encoding="utf-8",
    )

    trade_csv.write_text(
        "timestamp,cycle_id,ticker,strategy,yes_price,no_price,shares,notional,fees,slippage,net_pnl,status,opened_at,closed_at,held_seconds,hold_note\n"
        "2026-02-18T01:01:01+00:00,C1,MKT-B,arb_yes_no_pair,0.48,0.49,10,9.7,0.01,0.01,0.28,filled,2026-02-18T01:01:01+00:00,2026-02-18T01:01:01+00:00,0.0,test\n"
        "2026-02-18T01:03:01+00:00,C1,MKT-C,arb_yes_no_pair,0.40,0.55,10,9.5,0.01,0.01,0.48,filled,2026-02-18T01:03:01+00:00,2026-02-18T01:03:01+00:00,0.0,test\n",
        encoding="utf-8",
    )

    summary = build_daily_summary(str(base), target_date="2026-02-18")

    assert summary["trades_executed"] == 2
    assert summary["total_paper_pnl"] == 0.76
    assert summary["total_executed_notional"] == 19.2
    assert summary["avg_pnl_per_trade"] == 0.38
    assert summary["avg_return_per_trade_pct"] == 3.958333
    assert summary["profitable_trades"] == 2
    assert summary["losing_trades"] == 0
    assert summary["breakeven_trades"] == 0
    assert summary["skip_reasons"]["No deterministic arbitrage found"] == 2
    assert summary["traded_markets"][0]["ticker"] in {"MKT-B", "MKT-C"}
    assert len(summary["trade_details"]) == 2
    assert all("ticker" in row for row in summary["trade_details"])

    top = summary["top_markets_by_arb_hit_rate"]
    assert top[0]["ticker"] in {"MKT-B", "MKT-C"}
    assert all("arb_hit_rate" in row for row in top)
