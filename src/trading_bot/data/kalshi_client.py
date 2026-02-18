from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from trading_bot.common import MarketSnapshot, OrderBookLevel, utc_now
from trading_bot.execution.live_guard import SafetyGuard


class KalshiDataClient:
    """Read-only Kalshi client for market data in paper mode."""

    def __init__(self, base_url: str, safety_guard: SafetyGuard, timeout_seconds: int = 10) -> None:
        self._base_url = base_url.rstrip("/")
        self._guard = safety_guard
        self._timeout_seconds = timeout_seconds

    def _build_url(self, path: str, params: Optional[Dict[str, Any]] = None) -> str:
        base = f"{self._base_url}/{path.lstrip('/')}"
        if not params:
            return base
        return f"{base}?{urlencode(params)}"

    def _get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = self._build_url(path, params)
        self._guard.block_live_endpoint(url, method="GET")
        request = Request(url=url, method="GET", headers={"Accept": "application/json"})
        with urlopen(request, timeout=self._timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def fetch_markets(self, limit: int = 100, status: str = "open") -> Dict[str, Any]:
        return self._get_json("markets", params={"limit": limit, "status": status})

    def fetch_orderbook(self, ticker: str) -> Dict[str, Any]:
        return self._get_json(f"markets/{ticker}/orderbook")

    def fetch_trades(self, ticker: str, limit: int = 100) -> Dict[str, Any]:
        return self._get_json(f"markets/{ticker}/trades", params={"limit": limit})

    def fetch_market_snapshot(self, ticker: str) -> MarketSnapshot:
        raw = self.fetch_orderbook(ticker)
        yes_ask = self._best_ask(self._extract_side_levels(raw, "yes"))
        no_ask = self._best_ask(self._extract_side_levels(raw, "no"))
        return MarketSnapshot(
            ticker=ticker,
            yes_ask=yes_ask,
            no_ask=no_ask,
            last_updated=utc_now(),
            source="kalshi-prod-data",
        )

    @staticmethod
    def _extract_side_levels(raw: Dict[str, Any], side: str) -> Iterable[Any]:
        if side in raw:
            return raw.get(side) or []
        if f"{side}_orders" in raw:
            return raw.get(f"{side}_orders") or []

        orderbook = raw.get("orderbook")
        if isinstance(orderbook, dict):
            if side in orderbook:
                return orderbook.get(side) or []
            if f"{side}_orders" in orderbook:
                return orderbook.get(f"{side}_orders") or []
        return []

    @staticmethod
    def _best_ask(levels: Iterable[Any]) -> OrderBookLevel:
        best_price: Optional[float] = None
        best_size: float = 0.0

        for level in levels:
            price, size = KalshiDataClient._parse_level(level)
            if price <= 0 or size <= 0:
                continue
            if best_price is None or price < best_price:
                best_price = price
                best_size = size

        if best_price is None:
            return OrderBookLevel(price=0.0, size=0.0)
        return OrderBookLevel(price=best_price, size=best_size)

    @staticmethod
    def _parse_level(level: Any) -> tuple[float, float]:
        try:
            if isinstance(level, dict):
                price = float(level.get("price", 0.0))
                size = float(level.get("size", level.get("quantity", 0.0)))
            elif isinstance(level, (list, tuple)) and len(level) >= 2:
                price = float(level[0])
                size = float(level[1])
            else:
                return 0.0, 0.0
        except (TypeError, ValueError):
            return 0.0, 0.0

        if price > 1.0:
            price /= 100.0
        return price, size
