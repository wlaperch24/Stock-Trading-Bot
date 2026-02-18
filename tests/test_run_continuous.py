from pathlib import Path

from trading_bot.config import AppConfig, load_default_config
from trading_bot import main as main_module


def _config(tmp_path: Path) -> AppConfig:
    cfg = load_default_config()
    cfg.execution.ledger_dir = str(tmp_path / "ledger")
    cfg.execution.selector_state_file = str(tmp_path / "selector_state.json")
    cfg.execution.market_cache_file = str(tmp_path / "market_cache.json")
    cfg.execution.max_consecutive_degraded_cycles = 2
    cfg.execution.degraded_cycle_sleep_seconds = 1
    cfg.validate()
    return cfg


def _result(status: str, reason: str = "Cycle complete") -> dict[str, object]:
    return {
        "cycle_status": status,
        "reason": reason,
        "selected_markets": 0,
        "scanned_markets": 0,
        "executed_trades": 0,
        "net_pnl": 0.0,
        "used_cached_candidates": False,
        "paused_for_review": False,
    }


def test_continuous_recovers_after_single_degraded_cycle(monkeypatch, tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    cfg.execution.preflight_connectivity_check = False
    sequence = iter([_result("degraded", "Market discovery failed"), _result("ok"), _result("ok")])
    calls = {"count": 0}

    def _fake_cycle(**kwargs):
        calls["count"] += 1
        return next(sequence)

    monkeypatch.setattr(main_module, "run_market_scan_cycle", _fake_cycle)
    monkeypatch.setattr(main_module.time, "sleep", lambda _: None)

    main_module.run_continuous(config=cfg, max_cycles=3)
    assert calls["count"] == 3


def test_continuous_stops_after_too_many_degraded_cycles(monkeypatch, tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    cfg.execution.preflight_connectivity_check = False
    calls = {"count": 0}

    def _fake_cycle(**kwargs):
        calls["count"] += 1
        return _result("degraded", "No candidate markets available")

    monkeypatch.setattr(main_module, "run_market_scan_cycle", _fake_cycle)
    monkeypatch.setattr(main_module.time, "sleep", lambda _: None)

    main_module.run_continuous(config=cfg, max_cycles=10)
    assert calls["count"] == 2


def test_continuous_stops_on_halted_cycle(monkeypatch, tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    cfg.execution.preflight_connectivity_check = False
    calls = {"count": 0}

    def _fake_cycle(**kwargs):
        calls["count"] += 1
        return _result("halted", "Daily loss stop reached")

    monkeypatch.setattr(main_module, "run_market_scan_cycle", _fake_cycle)
    monkeypatch.setattr(main_module.time, "sleep", lambda _: None)

    main_module.run_continuous(config=cfg, max_cycles=10)
    assert calls["count"] == 1


def test_continuous_honors_max_runtime_seconds(monkeypatch, tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    cfg.execution.preflight_connectivity_check = False
    calls = {"count": 0}

    def _fake_cycle(**kwargs):
        calls["count"] += 1
        return _result("ok")

    monkeypatch.setattr(main_module, "run_market_scan_cycle", _fake_cycle)
    monkeypatch.setattr(main_module.time, "sleep", lambda _: None)

    main_module.run_continuous(config=cfg, max_cycles=10, max_runtime_seconds=0)
    assert calls["count"] == 1


def test_continuous_exits_early_when_preflight_fails(monkeypatch, tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    calls = {"count": 0}

    def _fake_cycle(**kwargs):
        calls["count"] += 1
        return _result("ok")

    monkeypatch.setattr(main_module, "run_market_scan_cycle", _fake_cycle)
    monkeypatch.setattr(main_module, "_preflight_data_connectivity", lambda runtime, config: (False, "dns failed"))
    monkeypatch.setattr(main_module.time, "sleep", lambda _: None)

    main_module.run_continuous(config=cfg, max_cycles=10)
    assert calls["count"] == 0
