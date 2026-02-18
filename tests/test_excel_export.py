from pathlib import Path
import zipfile

from trading_bot.monitoring import export_trades_to_excel


def test_export_trades_to_excel_creates_xlsx_with_totals(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger"
    ledger.mkdir(parents=True, exist_ok=True)
    trade_csv = ledger / "trade_log.csv"

    trade_csv.write_text(
        "timestamp,cycle_id,ticker,strategy,yes_price,no_price,shares,notional,fees,slippage,net_pnl,status,opened_at,closed_at,held_seconds,hold_note\n"
        "2026-02-18T01:01:01+00:00,C1,MKT-WIN,arb_yes_no_pair,0.48,0.49,10,100,0.08,0.10,2.91,filled,2026-02-18T01:01:01+00:00,2026-02-18T01:01:01+00:00,0.0,test\n"
        "2026-02-18T01:02:01+00:00,C1,MKT-LOSS,arb_yes_no_pair,0.52,0.50,10,100,0.08,0.10,-1.50,filled,2026-02-18T01:02:01+00:00,2026-02-18T01:02:01+00:00,0.0,test\n",
        encoding="utf-8",
    )

    out = tmp_path / "report.xlsx"
    report = export_trades_to_excel(str(ledger), output_path=str(out), target_date="2026-02-18")

    assert out.exists()
    assert report["trades_exported"] == 2
    assert report["grand_net_total"] == 1.41

    with zipfile.ZipFile(out, "r") as archive:
        sheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")

    assert "Grand Net Total" in sheet_xml
    assert "MKT-WIN" in sheet_xml
    assert "MKT-LOSS" in sheet_xml
