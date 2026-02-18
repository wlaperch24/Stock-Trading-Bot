"""Kalshi paper-only arbitrage runner (V1)."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from typing import Any

from trading_bot.common import DecisionAction, MarketSnapshot, OrderBookLevel, utc_now
from trading_bot.config import AppConfig, load_default_config
from trading_bot.data import KalshiDataClient
from trading_bot.decision import DecisionPolicy
from trading_bot.execution import PaperExecutionEngine, SafetyGuard
from trading_bot.monitoring import CsvLedgerStore, Reporter
from trading_bot.risk import RiskManager
from trading_bot.signals import AdaptiveMarketSelector, ArbitrageDetector


def build_sample_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        ticker="SAMPLE-KALSHI-MARKET",
        yes_ask=OrderBookLevel(price=0.48, size=400.0),
        no_ask=OrderBookLevel(price=0.49, size=400.0),
        last_updated=utc_now(),
        source="sample",
    )


@dataclass
class RuntimeContext:
    reporter: Reporter
    risk_manager: RiskManager
    data_client: KalshiDataClient
    detector: ArbitrageDetector
    policy: DecisionPolicy
    engine: PaperExecutionEngine
    ledger: CsvLedgerStore


def _build_runtime(cfg: AppConfig) -> RuntimeContext:
    reporter = Reporter()
    risk_manager = RiskManager(cfg.risk)
    guard = SafetyGuard(cfg, on_critical=reporter.critical)
    guard.assert_paper_only()
    data_client = KalshiDataClient(
        cfg.kalshi_base_url,
        guard,
        max_retries=cfg.execution.http_max_retries,
        retry_backoff_seconds=cfg.execution.http_retry_backoff_seconds,
    )

    detector = ArbitrageDetector(
        fee_bps=cfg.execution.fee_bps,
        slippage_bps=cfg.execution.slippage_bps,
        min_net_edge=cfg.execution.min_net_edge,
    )
    policy = DecisionPolicy(cfg, risk_manager)
    engine = PaperExecutionEngine(cfg, risk_manager, reporter)
    ledger = CsvLedgerStore(cfg.execution.ledger_dir)
    return RuntimeContext(
        reporter=reporter,
        risk_manager=risk_manager,
        data_client=data_client,
        detector=detector,
        policy=policy,
        engine=engine,
        ledger=ledger,
    )


def _build_selector(cfg: AppConfig) -> AdaptiveMarketSelector:
    return AdaptiveMarketSelector(
        scan_limit=cfg.execution.market_scan_limit,
        min_observations=cfg.execution.min_observations_before_deprioritize,
        exploration_size=cfg.execution.exploration_markets_per_cycle,
    )


def _save_market_cache(path: str, candidates: list[object]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = []
    for candidate in candidates:
        ticker = getattr(candidate, "ticker", None)
        liquidity = getattr(candidate, "liquidity_score", None)
        category = getattr(candidate, "category", None)
        if not isinstance(ticker, str):
            continue
        payload.append(
            {
                "ticker": ticker,
                "liquidity_score": float(liquidity or 0.0),
                "category": str(category or "unknown"),
            }
        )
    file_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _load_market_cache(path: str) -> list[object]:
    from trading_bot.common import MarketDescriptor

    file_path = Path(path)
    if not file_path.exists():
        return []
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []

    candidates = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        ticker = item.get("ticker")
        if not isinstance(ticker, str) or not ticker.strip():
            continue
        try:
            liquidity_score = float(item.get("liquidity_score", 0.0))
        except (TypeError, ValueError):
            liquidity_score = 0.0
        category = str(item.get("category", "unknown"))
        candidates.append(MarketDescriptor(ticker=ticker, liquidity_score=liquidity_score, category=category))
    return candidates


def run_once(
    config: AppConfig | None = None,
    snapshot: MarketSnapshot | None = None,
    ticker: str | None = None,
) -> dict[str, object]:
    cfg = config or load_default_config()
    cfg.validate()

    runtime = _build_runtime(cfg)
    cycle_id = utc_now().strftime("%Y%m%dT%H%M%S%fZ")

    if snapshot is not None:
        market_snapshot = snapshot
    elif ticker:
        try:
            market_snapshot = runtime.data_client.fetch_market_snapshot(ticker)
        except Exception as exc:  # pragma: no cover - network path is environment-dependent
            runtime.reporter.critical(f"Failed to fetch market snapshot for {ticker}: {exc}")
            runtime.risk_manager.halt("Market data fetch failed")
            runtime.ledger.append_decision(
                cycle_id=cycle_id,
                snapshot=MarketSnapshot(
                    ticker=ticker,
                    yes_ask=OrderBookLevel(price=0.0, size=0.0),
                    no_ask=OrderBookLevel(price=0.0, size=0.0),
                    last_updated=utc_now(),
                    source="fetch_error",
                ),
                decision=DecisionAction.HALT,
                reason=f"Market data fetch failed: {exc}",
                opportunity=None,
                executed_status="not_attempted",
            )
            return {
                "decision": DecisionAction.HALT.value,
                "reason": "Market data fetch failed",
                "execution_status": "not_attempted",
                "net_pnl": 0.0,
                "win_rate": 0.0,
                "paused_for_review": False,
                "critical_alerts": runtime.reporter.critical_alerts,
                "daily_report": {},
                "decision_log_path": str(runtime.ledger.decision_file),
                "trade_log_path": str(runtime.ledger.trade_file),
            }
    else:
        market_snapshot = build_sample_snapshot()

    opportunity = runtime.detector.detect(market_snapshot)
    decision = runtime.policy.evaluate(market_snapshot, opportunity)

    executed_status = "not_attempted"
    if decision.action == DecisionAction.EXECUTE_PAPER and decision.intent and decision.opportunity:
        fill = runtime.engine.simulate_arb_pair(decision.intent, decision.opportunity, market_snapshot)
        executed_status = fill.status
        if fill.status == "filled":
            runtime.ledger.append_trade(cycle_id=cycle_id, intent=decision.intent, fill=fill)

    runtime.ledger.append_decision(
        cycle_id=cycle_id,
        snapshot=market_snapshot,
        decision=decision.action,
        reason=decision.reason,
        opportunity=decision.opportunity,
        executed_status=executed_status,
    )

    performance = runtime.engine.performance()
    red_day_paused = runtime.risk_manager.apply_red_day_policy()
    daily_report = runtime.reporter.build_daily_report(performance, runtime.risk_manager.state)

    return {
        "decision": decision.action.value,
        "reason": decision.reason,
        "execution_status": executed_status,
        "net_pnl": performance.net_pnl,
        "win_rate": performance.win_rate,
        "paused_for_review": red_day_paused,
        "critical_alerts": runtime.reporter.critical_alerts,
        "daily_report": daily_report,
        "decision_log_path": str(runtime.ledger.decision_file),
        "trade_log_path": str(runtime.ledger.trade_file),
    }


def run_market_scan_cycle(
    config: AppConfig | None = None,
    selector: AdaptiveMarketSelector | None = None,
    runtime: RuntimeContext | None = None,
) -> dict[str, Any]:
    cfg = config or load_default_config()
    cfg.validate()
    runtime = runtime or _build_runtime(cfg)
    cycle_id = utc_now().strftime("%Y%m%dT%H%M%S%fZ")

    selector_created = selector is None
    selector = selector or _build_selector(cfg)
    if selector_created:
        selector.load_state(cfg.execution.selector_state_file)
    used_cached_candidates = False

    try:
        candidates = runtime.data_client.discover_open_markets(
            limit=cfg.execution.market_scan_limit,
            pool_limit=cfg.execution.market_candidate_pool_limit,
            min_liquidity=cfg.execution.min_market_liquidity,
        )
        if candidates:
            _save_market_cache(cfg.execution.market_cache_file, candidates)
        else:
            candidates = _load_market_cache(cfg.execution.market_cache_file)
            used_cached_candidates = bool(candidates)
    except Exception as exc:  # pragma: no cover - network path is environment-dependent
        runtime.reporter.critical(f"Failed to discover markets: {exc}")
        candidates = _load_market_cache(cfg.execution.market_cache_file)
        used_cached_candidates = bool(candidates)
        if not used_cached_candidates:
            runtime.risk_manager.halt("Market discovery failed")
            selector.save_state(cfg.execution.selector_state_file)
            return {
                "cycle_status": "halted",
                "reason": "Market discovery failed",
                "candidate_markets": 0,
                "selected_markets": 0,
                "scanned_markets": 0,
                "executed_trades": 0,
                "skipped_markets": 0,
                "net_pnl": 0.0,
                "paused_for_review": False,
                "critical_alerts": runtime.reporter.critical_alerts,
                "top_market_stats": selector.snapshot_stats(),
                "decision_log_path": str(runtime.ledger.decision_file),
                "trade_log_path": str(runtime.ledger.trade_file),
                "used_cached_candidates": False,
            }

    if used_cached_candidates:
        runtime.reporter.critical("Using cached market universe due discovery failure/empty response")

    if not candidates:
        runtime.risk_manager.halt("No candidate markets available")
        selector.save_state(cfg.execution.selector_state_file)
        return {
            "cycle_status": "halted",
            "reason": "No candidate markets available",
            "candidate_markets": 0,
            "selected_markets": 0,
            "scanned_markets": 0,
            "executed_trades": 0,
            "skipped_markets": 0,
            "net_pnl": 0.0,
            "paused_for_review": False,
            "critical_alerts": runtime.reporter.critical_alerts,
            "top_market_stats": selector.snapshot_stats(),
            "decision_log_path": str(runtime.ledger.decision_file),
            "trade_log_path": str(runtime.ledger.trade_file),
            "used_cached_candidates": used_cached_candidates,
        }

    selected = selector.select_market_batch(candidates)[: cfg.execution.market_scan_limit]

    scanned_markets = 0
    executed_trades = 0
    skipped_markets = 0

    for market in selected:
        scanned_markets += 1
        try:
            snapshot = runtime.data_client.fetch_market_snapshot(market.ticker)
        except Exception as exc:  # pragma: no cover - network path is environment-dependent
            runtime.reporter.record_missed(market.ticker, f"Snapshot fetch failed: {exc}")
            runtime.ledger.append_decision(
                cycle_id=cycle_id,
                snapshot=MarketSnapshot(
                    ticker=market.ticker,
                    yes_ask=OrderBookLevel(price=0.0, size=0.0),
                    no_ask=OrderBookLevel(price=0.0, size=0.0),
                    last_updated=utc_now(),
                    source="fetch_error",
                ),
                decision=DecisionAction.SKIP,
                reason=f"Snapshot fetch failed: {exc}",
                opportunity=None,
                executed_status="skipped_fetch_error",
            )
            skipped_markets += 1
            continue

        opportunity = runtime.detector.detect(snapshot)
        selector.observe_market(
            ticker=market.ticker,
            had_arbitrage=opportunity is not None,
            edge_per_share=opportunity.net_edge_per_share if opportunity else 0.0,
        )

        decision = runtime.policy.evaluate(snapshot, opportunity)
        executed_status = "not_attempted"
        if decision.action == DecisionAction.EXECUTE_PAPER and decision.intent and decision.opportunity:
            fill = runtime.engine.simulate_arb_pair(decision.intent, decision.opportunity, snapshot)
            if fill.status == "filled":
                executed_trades += 1
                selector.record_trade_result(market.ticker, profitable=fill.net_pnl > 0)
                runtime.ledger.append_trade(cycle_id=cycle_id, intent=decision.intent, fill=fill)
                executed_status = "filled"
            else:
                skipped_markets += 1
                executed_status = fill.status
        elif decision.action == DecisionAction.HALT:
            skipped_markets += 1
            executed_status = "halted_by_policy"
        else:
            skipped_markets += 1
            executed_status = "skipped"

        runtime.ledger.append_decision(
            cycle_id=cycle_id,
            snapshot=snapshot,
            decision=decision.action,
            reason=decision.reason,
            opportunity=decision.opportunity,
            executed_status=executed_status,
        )

        if runtime.risk_manager.state.halted:
            break

    performance = runtime.engine.performance()
    red_day_paused = runtime.risk_manager.apply_red_day_policy()
    runtime.reporter.build_daily_report(performance, runtime.risk_manager.state)
    selector.save_state(cfg.execution.selector_state_file)

    return {
        "cycle_status": "ok" if not runtime.risk_manager.state.halted else "halted",
        "reason": runtime.risk_manager.state.halt_reason or "Cycle complete",
        "candidate_markets": len(candidates),
        "selected_markets": len(selected),
        "scanned_markets": scanned_markets,
        "executed_trades": executed_trades,
        "skipped_markets": skipped_markets,
        "net_pnl": performance.net_pnl,
        "paused_for_review": red_day_paused,
        "critical_alerts": runtime.reporter.critical_alerts,
        "top_market_stats": selector.snapshot_stats(),
        "decision_log_path": str(runtime.ledger.decision_file),
        "trade_log_path": str(runtime.ledger.trade_file),
        "used_cached_candidates": used_cached_candidates,
    }


def run_continuous(config: AppConfig | None = None, max_cycles: int | None = None) -> None:
    cfg = config or load_default_config()
    cfg.validate()
    selector = _build_selector(cfg)
    selector.load_state(cfg.execution.selector_state_file)
    runtime = _build_runtime(cfg)

    cycle = 0
    current_day = utc_now().date()
    while True:
        new_day = utc_now().date()
        if new_day != current_day:
            runtime.risk_manager.reset_day()
            runtime.engine.ledger.clear()
            runtime.reporter.trade_records.clear()
            runtime.reporter.missed_records.clear()
            runtime.reporter.critical_alerts.clear()
            current_day = new_day

        cycle += 1
        result = run_market_scan_cycle(config=cfg, selector=selector, runtime=runtime)
        print(
            f"Cycle {cycle}: status={result['cycle_status']} selected={result['selected_markets']} "
            f"scanned={result['scanned_markets']} executed={result['executed_trades']} "
            f"net_pnl={result['net_pnl']:.4f} cached={result['used_cached_candidates']}"
        )

        if result["cycle_status"] == "halted" or result["paused_for_review"]:
            break
        if max_cycles is not None and cycle >= max_cycles:
            break

        time.sleep(cfg.execution.cadence_seconds)


def main() -> None:
    ticker = os.getenv("KALSHI_MARKET_TICKER")
    continuous = os.getenv("KALSHI_CONTINUOUS", "0") == "1"
    max_cycles_raw = os.getenv("KALSHI_MAX_CYCLES", "")
    max_cycles = int(max_cycles_raw) if max_cycles_raw.isdigit() else None

    if ticker:
        result = run_once(ticker=ticker)
        print("Execution mode: paper-only")
        print(f"Decision: {result['decision']} ({result['reason']})")
        print(f"Execution status: {result['execution_status']}")
        print(f"Net PnL (paper): {result['net_pnl']:.4f}")
        print(f"Win rate (paper): {result['win_rate']:.2%}")
        print(f"Paused for review: {result['paused_for_review']}")
        print(f"Decision log: {result['decision_log_path']}")
        print(f"Trade log: {result['trade_log_path']}")
        return

    if continuous:
        run_continuous(max_cycles=max_cycles)
        return

    cycle = run_market_scan_cycle()
    print("Execution mode: paper-only")
    print(f"Cycle status: {cycle['cycle_status']} ({cycle['reason']})")
    print(f"Markets candidate/selected/scanned: {cycle['candidate_markets']}/{cycle['selected_markets']}/{cycle['scanned_markets']}")
    print(f"Executed trades: {cycle['executed_trades']}")
    print(f"Net PnL (paper): {cycle['net_pnl']:.4f}")
    print(f"Paused for review: {cycle['paused_for_review']}")
    print(f"Decision log: {cycle['decision_log_path']}")
    print(f"Trade log: {cycle['trade_log_path']}")


if __name__ == "__main__":
    main()
