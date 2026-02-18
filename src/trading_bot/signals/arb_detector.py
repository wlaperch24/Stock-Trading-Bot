from __future__ import annotations

from datetime import timedelta
from typing import Optional

from trading_bot.common import ArbOpportunity, MarketSnapshot, utc_now


class ArbitrageDetector:
    def __init__(self, fee_bps: float, slippage_bps: float, min_net_edge: float = 0.0) -> None:
        self._fee_bps = fee_bps
        self._slippage_bps = slippage_bps
        self._min_net_edge = min_net_edge

    def detect(self, snapshot: MarketSnapshot, expiry_seconds: int = 10) -> Optional[ArbOpportunity]:
        if snapshot.yes_ask.price <= 0 or snapshot.no_ask.price <= 0:
            return None

        gross_cost = snapshot.yes_ask.price + snapshot.no_ask.price
        if gross_cost >= 1.0:
            return None

        fees = gross_cost * (self._fee_bps / 10000.0)
        slippage = gross_cost * (self._slippage_bps / 10000.0)
        net_edge = 1.0 - (gross_cost + fees + slippage)

        if net_edge <= self._min_net_edge:
            return None

        return ArbOpportunity(
            ticker=snapshot.ticker,
            yes_price=snapshot.yes_ask.price,
            no_price=snapshot.no_ask.price,
            shares_available=min(snapshot.yes_ask.size, snapshot.no_ask.size),
            gross_cost_per_share=gross_cost,
            fees_per_share=fees,
            slippage_per_share=slippage,
            net_edge_per_share=net_edge,
            confidence_class="deterministic",
            expires_at=utc_now() + timedelta(seconds=expiry_seconds),
        )
