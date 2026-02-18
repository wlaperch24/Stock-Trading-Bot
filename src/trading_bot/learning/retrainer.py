from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class ModelMetrics:
    expected_value_per_trade: float
    win_rate: float
    calibration_error: float
    max_drawdown: float


@dataclass(frozen=True)
class RetrainResult:
    promoted: bool
    reasons: List[str]


class NightlyRetrainer:
    def __init__(self, max_calibration_error: float = 0.03, max_drawdown: float = 300.0) -> None:
        self._max_calibration_error = max_calibration_error
        self._max_drawdown = max_drawdown

    def evaluate_and_promote(self, baseline: ModelMetrics, candidate: ModelMetrics) -> RetrainResult:
        reasons: List[str] = []

        if candidate.expected_value_per_trade <= baseline.expected_value_per_trade:
            reasons.append("candidate EV is not better than baseline")
        if candidate.win_rate < baseline.win_rate:
            reasons.append("candidate win rate regressed")
        if candidate.calibration_error > self._max_calibration_error:
            reasons.append("candidate calibration error too high")
        if candidate.max_drawdown > self._max_drawdown:
            reasons.append("candidate drawdown exceeds limit")

        return RetrainResult(promoted=len(reasons) == 0, reasons=reasons)
