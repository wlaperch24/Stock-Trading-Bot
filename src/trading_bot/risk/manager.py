from __future__ import annotations

from trading_bot.common import RiskState
from trading_bot.config import RiskConfig


class RiskManager:
    def __init__(self, config: RiskConfig) -> None:
        self._config = config
        self.state = RiskState()

    def can_open_notional(self, notional: float) -> bool:
        if self.state.halted or self.state.paused_for_review:
            return False
        if notional <= 0:
            return False
        if notional > self._config.max_dollars_per_trade:
            return False
        if (self.state.open_exposure + notional) > self._config.max_total_exposure:
            return False
        return True

    def remaining_trade_capacity(self) -> float:
        remaining_exposure = max(self._config.max_total_exposure - self.state.open_exposure, 0.0)
        return min(max(self._config.max_dollars_per_trade, 0.0), remaining_exposure)

    def reserve_exposure(self, notional: float) -> None:
        self.state.open_exposure += notional

    def release_exposure(self, notional: float) -> None:
        self.state.open_exposure = max(0.0, self.state.open_exposure - notional)

    def record_realized_pnl(self, pnl: float) -> None:
        self.state.realized_pnl += pnl
        if self.state.realized_pnl <= -abs(self._config.max_daily_loss):
            self.state.daily_loss_stop_hit = True
            self.halt("Daily loss stop reached")

    def halt(self, reason: str) -> None:
        self.state.halted = True
        self.state.halt_reason = reason

    def apply_red_day_policy(self) -> bool:
        if self._config.red_day_pause and self.state.realized_pnl < 0:
            self.state.paused_for_review = True
            self.state.halted = True
            self.state.halt_reason = "Negative day detected; paused for review"
            return True
        return False

    def reset_day(self) -> None:
        self.state.open_exposure = 0.0
        self.state.realized_pnl = 0.0
        self.state.daily_loss_stop_hit = False
        self.state.halted = False
        self.state.paused_for_review = False
        self.state.halt_reason = None
