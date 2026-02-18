from __future__ import annotations

import json
import signal
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from trading_bot.common import MarketDescriptor, MarketSnapshot, OrderBookLevel, utc_now
from trading_bot.execution.live_guard import SafetyGuard


class KalshiDataClient:
    """Read-only Kalshi client for market data in paper mode."""

    def __init__(
        self,
        base_url: str,
        safety_guard: SafetyGuard,
        timeout_seconds: int = 10,
        hard_timeout_seconds: int = 20,
        disable_system_proxy: bool = True,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._guard = safety_guard
        self._timeout_seconds = timeout_seconds
        self._hard_timeout_seconds = max(1, hard_timeout_seconds)
        self._disable_system_proxy = disable_system_proxy
        self._max_retries = max(0, max_retries)
        self._retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self._opener = build_opener(ProxyHandler({})) if self._disable_system_proxy else None

    def _build_url(self, path: str, params: Optional[Dict[str, Any]] = None) -> str:
        base = f"{self._base_url}/{path.lstrip('/')}"
        if not params:
            return base
        return f"{base}?{urlencode(params)}"

    def _get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = self._build_url(path, params)
        self._guard.block_live_endpoint(url, method="GET")
        request = Request(url=url, method="GET", headers={"Accept": "application/json"})

        for attempt in range(self._max_retries + 1):
            try:
                with self._hard_timeout():
                    with self._open_request(request) as response:
                        return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                if not self._should_retry_http(exc.code) or attempt >= self._max_retries:
                    raise
            except (URLError, TimeoutError, json.JSONDecodeError, OSError):
                if attempt >= self._max_retries:
                    raise

            time.sleep(self._retry_backoff_seconds * (attempt + 1))

        raise RuntimeError("Unreachable retry state")

    def _open_request(self, request: Request):
        if self._opener is not None:
            return self._opener.open(request, timeout=self._timeout_seconds)
        return urlopen(request, timeout=self._timeout_seconds)

    @contextmanager
    def _hard_timeout(self):
        if not hasattr(signal, "SIGALRM") or not hasattr(signal, "setitimer"):
            yield
            return
        if threading.current_thread() is not threading.main_thread():
            yield
            return

        previous_handler = signal.getsignal(signal.SIGALRM)
        previous_timer = signal.setitimer(signal.ITIMER_REAL, 0)

        def _raise_timeout(signum, frame):
            raise TimeoutError(f"HTTP request hard timeout exceeded ({self._hard_timeout_seconds}s)")

        signal.signal(signal.SIGALRM, _raise_timeout)
        signal.setitimer(signal.ITIMER_REAL, float(self._hard_timeout_seconds))
        try:
            yield
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
            if previous_timer[0] > 0 or previous_timer[1] > 0:
                signal.setitimer(signal.ITIMER_REAL, previous_timer[0], previous_timer[1])

    @staticmethod
    def _should_retry_http(status_code: int) -> bool:
        return status_code in (408, 425, 429, 500, 502, 503, 504)

    def fetch_markets(self, limit: int = 100, status: str = "open", cursor: str | None = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "status": status}
        if cursor:
            params["cursor"] = cursor
        return self._get_json("markets", params=params)

    def fetch_orderbook(self, ticker: str) -> Dict[str, Any]:
        return self._get_json(f"markets/{ticker}/orderbook")

    def fetch_trades(self, ticker: str, limit: int = 100) -> Dict[str, Any]:
        return self._get_json(f"markets/{ticker}/trades", params={"limit": limit})

    def discover_open_markets(self, limit: int = 200, pool_limit: int = 600, min_liquidity: float = 0.0) -> List[MarketDescriptor]:
        page_size = 100
        cursor: str | None = None
        collected: Dict[str, MarketDescriptor] = {}

        while len(collected) < max(pool_limit, limit):
            payload = self.fetch_markets(limit=page_size, status="open", cursor=cursor)
            raw_markets = payload.get("markets") or payload.get("data") or []
            if not isinstance(raw_markets, list) or not raw_markets:
                break

            for raw in raw_markets:
                market = self._parse_market_descriptor(raw)
                if market is None:
                    continue
                if market.liquidity_score < min_liquidity:
                    continue
                collected[market.ticker] = market
                if len(collected) >= max(pool_limit, limit):
                    break

            cursor = payload.get("cursor")
            if not cursor:
                break

        return sorted(collected.values(), key=lambda m: (m.liquidity_score, m.ticker), reverse=True)

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
    def _parse_market_descriptor(raw: Any) -> MarketDescriptor | None:
        if not isinstance(raw, dict):
            return None

        ticker = str(
            raw.get("ticker")
            or raw.get("symbol")
            or raw.get("market_ticker")
            or ""
        ).strip()
        if not ticker:
            return None

        category = str(raw.get("category") or raw.get("series_ticker") or "unknown")
        liquidity = KalshiDataClient._extract_numeric(
            raw,
            keys=("liquidity", "liquidity_score", "volume", "volume_24h", "open_interest", "total_volume"),
            default=0.0,
        )
        return MarketDescriptor(ticker=ticker, liquidity_score=liquidity, category=category)

    @staticmethod
    def _extract_numeric(raw: Dict[str, Any], keys: tuple[str, ...], default: float = 0.0) -> float:
        for key in keys:
            if key not in raw:
                continue
            value = raw.get(key)
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return default

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
