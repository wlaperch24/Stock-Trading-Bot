from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ExecutionMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class DecisionAction(str, Enum):
    EXECUTE_PAPER = "execute_paper"
    SKIP = "skip"
    HALT = "halt"


@dataclass(frozen=True)
class OrderBookLevel:
    price: float
    size: float


@dataclass(frozen=True)
class MarketSnapshot:
    ticker: str
    yes_ask: OrderBookLevel
    no_ask: OrderBookLevel
    last_updated: datetime
    source: str = "kalshi"


@dataclass(frozen=True)
class MarketDescriptor:
    ticker: str
    liquidity_score: float = 0.0
    category: str = "unknown"


@dataclass(frozen=True)
class ArbOpportunity:
    ticker: str
    yes_price: float
    no_price: float
    shares_available: float
    gross_cost_per_share: float
    fees_per_share: float
    slippage_per_share: float
    net_edge_per_share: float
    confidence_class: str
    expires_at: datetime


@dataclass(frozen=True)
class TradeIntent:
    ticker: str
    strategy: str
    yes_price: float
    no_price: float
    shares: float
    notional: float


@dataclass(frozen=True)
class PaperFill:
    ticker: str
    shares: float
    notional: float
    gross_payout: float
    fees: float
    slippage: float
    net_pnl: float
    filled_at: datetime
    status: str = "filled"


@dataclass(frozen=True)
class DailyPerformance:
    date: str
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    net_pnl: float
    missed_opportunities: int
    paused_for_review: bool = False


@dataclass
class RiskState:
    open_exposure: float = 0.0
    realized_pnl: float = 0.0
    daily_loss_stop_hit: bool = False
    halted: bool = False
    paused_for_review: bool = False
    halt_reason: Optional[str] = None


@dataclass(frozen=True)
class DecisionResult:
    action: DecisionAction
    reason: str
    intent: Optional[TradeIntent] = None
    opportunity: Optional[ArbOpportunity] = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
