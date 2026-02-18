from pathlib import Path

from trading_bot.common import DecisionAction, MarketSnapshot, OrderBookLevel, utc_now
from trading_bot.config import load_default_config
from trading_bot.main import run_once


def test_no_opportunity_results_in_skip_not_forced_trade(tmp_path: Path) -> None:
    config = load_default_config()
    config.execution.ledger_dir = str(tmp_path / "ledger")

    snapshot = MarketSnapshot(
        ticker="NO-ARB",
        yes_ask=OrderBookLevel(price=0.65, size=100.0),
        no_ask=OrderBookLevel(price=0.50, size=100.0),
        last_updated=utc_now(),
    )

    result = run_once(config=config, snapshot=snapshot)

    assert result["decision"] == DecisionAction.SKIP.value
    assert result["execution_status"] == "not_attempted"


def test_ledger_files_written_with_decisions_and_trades(tmp_path: Path) -> None:
    config = load_default_config()
    config.execution.ledger_dir = str(tmp_path / "ledger")

    snapshot = MarketSnapshot(
        ticker="HAS-ARB",
        yes_ask=OrderBookLevel(price=0.48, size=200.0),
        no_ask=OrderBookLevel(price=0.49, size=200.0),
        last_updated=utc_now(),
    )

    result = run_once(config=config, snapshot=snapshot)
    assert result["decision"] == DecisionAction.EXECUTE_PAPER.value

    decision_log = Path(result["decision_log_path"])
    trade_log = Path(result["trade_log_path"])

    assert decision_log.exists()
    assert trade_log.exists()

    decision_rows = decision_log.read_text(encoding="utf-8").strip().splitlines()
    trade_rows = trade_log.read_text(encoding="utf-8").strip().splitlines()

    assert len(decision_rows) >= 2
    assert len(trade_rows) >= 2
    assert "held_seconds" in trade_rows[0]
