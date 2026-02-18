from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from trading_bot.common import ExecutionMode


@dataclass
class RiskConfig:
    max_dollars_per_trade: float = 100.0
    max_total_exposure: float = 500.0
    max_daily_loss: float = 300.0
    starting_capital: float = 5000.0
    red_day_pause: bool = True


@dataclass
class ExecutionConfig:
    mode: ExecutionMode = ExecutionMode.PAPER
    cadence_seconds: int = 300
    fee_bps: float = 8.0
    slippage_bps: float = 10.0
    min_net_edge: float = 0.0
    v1_paper_only: bool = True


@dataclass
class SafetyConfig:
    allowed_data_hosts: Tuple[str, ...] = (
        "api.kalshi.com",
        "trading-api.kalshi.com",
    )
    allowed_data_path_fragments: Tuple[str, ...] = (
        "/markets",
        "/orderbook",
        "/trades",
        "/events",
        "/series",
    )
    blocked_path_fragments: Tuple[str, ...] = (
        "/orders",
        "/portfolio",
        "/positions",
        "/fills",
        "/create-order",
        "/batch/orders",
    )


@dataclass
class ProfitTargetConfig:
    daily_target: float = 1000.0
    guarantee: bool = False


@dataclass
class ModelConfig:
    strategy_priority: str = "arbitrage_only_until_stable"
    predictive_enabled: bool = False
    retrain_frequency: str = "daily"
    promotion_policy: str = "guarded"


@dataclass
class AppConfig:
    risk: RiskConfig = field(default_factory=RiskConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    target: ProfitTargetConfig = field(default_factory=ProfitTargetConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    kalshi_base_url: str = "https://api.kalshi.com/trade-api/v2"

    def validate(self) -> None:
        if self.execution.v1_paper_only and self.execution.mode != ExecutionMode.PAPER:
            raise ValueError("V1 runtime is hard-locked to paper mode.")
        if self.risk.max_dollars_per_trade <= 0:
            raise ValueError("max_dollars_per_trade must be positive.")
        if self.risk.max_total_exposure <= 0:
            raise ValueError("max_total_exposure must be positive.")
        if self.risk.starting_capital <= 0:
            raise ValueError("starting_capital must be positive.")
        if self.risk.max_dollars_per_trade > self.risk.starting_capital:
            raise ValueError("max_dollars_per_trade cannot exceed starting capital.")
        if self.risk.max_total_exposure > self.risk.starting_capital:
            raise ValueError("max_total_exposure cannot exceed starting capital.")
        if self.execution.cadence_seconds < 60:
            raise ValueError("cadence_seconds must be at least 60 seconds.")


def load_default_config() -> AppConfig:
    config = AppConfig()
    config.validate()
    return config
