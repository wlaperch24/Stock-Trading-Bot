from __future__ import annotations

from typing import Callable, Optional
from urllib.parse import urlparse

from trading_bot.common import ExecutionMode
from trading_bot.config import AppConfig


class LiveTradeBlockedError(RuntimeError):
    """Raised when code attempts a live-trading action in paper mode."""


class SafetyGuard:
    def __init__(
        self,
        config: AppConfig,
        on_critical: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._config = config
        self._on_critical = on_critical

    def _raise_critical(self, message: str) -> None:
        if self._on_critical is not None:
            self._on_critical(message)
        raise LiveTradeBlockedError(message)

    def assert_paper_only(self) -> None:
        if self._config.execution.mode != ExecutionMode.PAPER:
            self._raise_critical("Execution mode is not paper. Halting.")

    def block_live_endpoint(self, url: str, method: str = "GET") -> None:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        path = parsed.path.lower()
        method_upper = method.upper()

        if self._config.execution.mode != ExecutionMode.PAPER:
            return

        if method_upper != "GET":
            self._raise_critical(f"Non-GET request blocked in paper mode: {method_upper} {url}")

        if host not in self._config.safety.allowed_data_hosts:
            self._raise_critical(f"Host not allowed in paper mode: {host}")

        for fragment in self._config.safety.blocked_path_fragments:
            if fragment in path:
                self._raise_critical(f"Blocked live-trading path in paper mode: {path}")

        if not any(fragment in path for fragment in self._config.safety.allowed_data_path_fragments):
            self._raise_critical(f"Non-market-data path blocked in paper mode: {path}")
