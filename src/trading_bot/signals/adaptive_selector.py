from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Dict, Iterable, List

from trading_bot.common import MarketDescriptor


@dataclass
class MarketPerformanceStats:
    observations: int = 0
    arb_hits: int = 0
    profitable_trades: int = 0
    cumulative_edge: float = 0.0


class AdaptiveMarketSelector:
    """Prioritizes markets by observed arbitrage quality while preserving exploration."""

    def __init__(self, scan_limit: int, min_observations: int, exploration_size: int) -> None:
        self._scan_limit = scan_limit
        self._min_observations = max(1, min_observations)
        self._exploration_size = max(0, exploration_size)
        self._stats: Dict[str, MarketPerformanceStats] = {}

    def observe_market(self, ticker: str, had_arbitrage: bool, edge_per_share: float = 0.0) -> None:
        stats = self._stats.setdefault(ticker, MarketPerformanceStats())
        stats.observations += 1
        if had_arbitrage:
            stats.arb_hits += 1
            stats.cumulative_edge += max(edge_per_share, 0.0)

    def record_trade_result(self, ticker: str, profitable: bool) -> None:
        stats = self._stats.setdefault(ticker, MarketPerformanceStats())
        if profitable:
            stats.profitable_trades += 1

    def select_market_batch(self, markets: Iterable[MarketDescriptor]) -> List[MarketDescriptor]:
        unique: Dict[str, MarketDescriptor] = {}
        for market in markets:
            if market.ticker not in unique:
                unique[market.ticker] = market

        available = list(unique.values())
        if len(available) <= self._scan_limit:
            return sorted(available, key=lambda market: self._market_score(market), reverse=True)

        by_least_observed = sorted(
            available,
            key=lambda market: (
                self._stats.get(market.ticker, MarketPerformanceStats()).observations,
                -market.liquidity_score,
                market.ticker,
            ),
        )
        warmup_markets = sorted(
            (
                market
                for market in available
                if 0 < self._stats.get(market.ticker, MarketPerformanceStats()).observations < self._min_observations
            ),
            key=lambda market: (
                -self._stats.get(market.ticker, MarketPerformanceStats()).observations,
                -market.liquidity_score,
                market.ticker,
            ),
        )
        by_score = sorted(available, key=lambda market: self._market_score(market), reverse=True)

        selected: Dict[str, MarketDescriptor] = {}
        for market in by_least_observed[: self._exploration_size]:
            selected[market.ticker] = market

        for market in warmup_markets:
            if len(selected) >= self._scan_limit:
                break
            selected.setdefault(market.ticker, market)

        for market in by_score:
            if len(selected) >= self._scan_limit:
                break
            selected.setdefault(market.ticker, market)

        return list(selected.values())

    def snapshot_stats(self, top_n: int = 10) -> List[dict[str, float | int | str]]:
        rows = []
        for ticker, stats in self._stats.items():
            hit_rate = float(stats.arb_hits / stats.observations) if stats.observations else 0.0
            avg_edge = float(stats.cumulative_edge / stats.arb_hits) if stats.arb_hits else 0.0
            rows.append(
                {
                    "ticker": ticker,
                    "observations": stats.observations,
                    "arb_hits": stats.arb_hits,
                    "hit_rate": round(hit_rate, 4),
                    "avg_edge": round(avg_edge, 4),
                    "profitable_trades": stats.profitable_trades,
                }
            )

        rows.sort(key=lambda row: (row["hit_rate"], row["avg_edge"], row["observations"]), reverse=True)
        return rows[:top_n]

    def save_state(self, path: str) -> None:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "scan_limit": self._scan_limit,
            "min_observations": self._min_observations,
            "exploration_size": self._exploration_size,
            "stats": {
                ticker: {
                    "observations": stats.observations,
                    "arb_hits": stats.arb_hits,
                    "profitable_trades": stats.profitable_trades,
                    "cumulative_edge": stats.cumulative_edge,
                }
                for ticker, stats in self._stats.items()
            },
        }
        file_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def load_state(self, path: str) -> bool:
        file_path = Path(path)
        if not file_path.exists():
            return False

        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False

        stats_payload = payload.get("stats")
        if not isinstance(stats_payload, dict):
            return False

        restored: Dict[str, MarketPerformanceStats] = {}
        for ticker, raw in stats_payload.items():
            if not isinstance(ticker, str) or not isinstance(raw, dict):
                continue
            try:
                restored[ticker] = MarketPerformanceStats(
                    observations=max(int(raw.get("observations", 0)), 0),
                    arb_hits=max(int(raw.get("arb_hits", 0)), 0),
                    profitable_trades=max(int(raw.get("profitable_trades", 0)), 0),
                    cumulative_edge=max(float(raw.get("cumulative_edge", 0.0)), 0.0),
                )
            except (TypeError, ValueError):
                continue

        self._stats = restored
        return True

    def _market_score(self, market: MarketDescriptor) -> float:
        stats = self._stats.get(market.ticker, MarketPerformanceStats())

        hit_rate = (stats.arb_hits + 1.0) / (stats.observations + 2.0)
        avg_edge = (stats.cumulative_edge / stats.arb_hits) if stats.arb_hits else 0.0
        profitability = (stats.profitable_trades / stats.arb_hits) if stats.arb_hits else 0.0
        liquidity_component = min(max(market.liquidity_score, 0.0), 10000.0) / 10000.0

        insufficient_data_bonus = 0.1 if stats.observations < self._min_observations else 0.0
        cold_market_penalty = 0.15 if stats.observations >= self._min_observations and stats.arb_hits == 0 else 0.0

        return (
            (hit_rate * 0.55)
            + (avg_edge * 0.25)
            + (profitability * 0.1)
            + (liquidity_component * 0.1)
            + insufficient_data_bonus
            - cold_market_penalty
        )
