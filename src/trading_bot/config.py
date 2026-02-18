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
    cadence_seconds: int = 600
    fee_bps: float = 8.0
    slippage_bps: float = 10.0
    min_net_edge: float = 0.0
    v1_paper_only: bool = True
    market_scan_limit: int = 200
    market_candidate_pool_limit: int = 600
    min_market_liquidity: float = 50.0
    min_observations_before_deprioritize: int = 8
    exploration_markets_per_cycle: int = 40
    ledger_dir: str = "data/ledger"
    selector_state_file: str = "data/ledger/market_selector_state.json"
    market_cache_file: str = "data/ledger/market_candidates_cache.json"
    http_max_retries: int = 2
    http_retry_backoff_seconds: float = 0.5


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
        if self.execution.market_scan_limit <= 0:
            raise ValueError("market_scan_limit must be positive.")
        if self.execution.market_candidate_pool_limit < self.execution.market_scan_limit:
            raise ValueError("market_candidate_pool_limit must be >= market_scan_limit.")
        if self.execution.min_market_liquidity < 0:
            raise ValueError("min_market_liquidity cannot be negative.")
        if self.execution.min_observations_before_deprioritize < 1:
            raise ValueError("min_observations_before_deprioritize must be >= 1.")
        if self.execution.exploration_markets_per_cycle < 0:
            raise ValueError("exploration_markets_per_cycle cannot be negative.")
        if not self.execution.ledger_dir.strip():
            raise ValueError("ledger_dir cannot be empty.")
        if not self.execution.selector_state_file.strip():
            raise ValueError("selector_state_file cannot be empty.")
        if not self.execution.market_cache_file.strip():
            raise ValueError("market_cache_file cannot be empty.")
        if self.execution.http_max_retries < 0:
            raise ValueError("http_max_retries cannot be negative.")
        if self.execution.http_retry_backoff_seconds < 0:
            raise ValueError("http_retry_backoff_seconds cannot be negative.")


def load_default_config() -> AppConfig:
    config = AppConfig()
    config.validate()
    return config
