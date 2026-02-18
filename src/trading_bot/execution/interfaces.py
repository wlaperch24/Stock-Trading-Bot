from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from trading_bot.common import ArbOpportunity, MarketSnapshot, PaperFill, TradeIntent


class ExecutionEngine(ABC):
    @abstractmethod
    def simulate_arb_pair(
        self,
        intent: TradeIntent,
        opportunity: ArbOpportunity,
        snapshot: MarketSnapshot,
    ) -> PaperFill:
        raise NotImplementedError

    @abstractmethod
    def place_live_order(self, order: Any) -> None:
        raise NotImplementedError
