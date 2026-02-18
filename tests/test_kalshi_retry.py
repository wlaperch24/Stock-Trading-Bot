import json
import signal
import time
from urllib.error import URLError

import pytest

from trading_bot.common import ExecutionMode
from trading_bot.config import AppConfig
from trading_bot.data.kalshi_client import KalshiDataClient
from trading_bot.execution import SafetyGuard


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_get_json_retries_on_transient_url_error(monkeypatch) -> None:
    config = AppConfig()
    config.execution.mode = ExecutionMode.PAPER
    guard = SafetyGuard(config)
    client = KalshiDataClient(
        config.kalshi_base_url,
        guard,
        max_retries=1,
        retry_backoff_seconds=0.0,
    )

    calls = {"count": 0}

    def _fake_open_request(request):
        calls["count"] += 1
        if calls["count"] == 1:
            raise URLError("temporary")
        return _FakeResponse({"markets": []})

    monkeypatch.setattr(client, "_open_request", _fake_open_request)

    payload = client.fetch_markets(limit=1)
    assert payload == {"markets": []}
    assert calls["count"] == 2


def test_get_json_hard_timeout_recovers_on_retry(monkeypatch) -> None:
    if not hasattr(signal, "SIGALRM"):
        pytest.skip("SIGALRM not available on this platform")

    config = AppConfig()
    config.execution.mode = ExecutionMode.PAPER
    guard = SafetyGuard(config)
    client = KalshiDataClient(
        config.kalshi_base_url,
        guard,
        timeout_seconds=10,
        hard_timeout_seconds=1,
        max_retries=1,
        retry_backoff_seconds=0.0,
    )

    calls = {"count": 0}

    def _fake_open_request(request):
        calls["count"] += 1
        if calls["count"] == 1:
            time.sleep(2.0)
            return _FakeResponse({"markets": []})
        return _FakeResponse({"markets": []})

    monkeypatch.setattr(client, "_open_request", _fake_open_request)

    payload = client.fetch_markets(limit=1)
    assert payload == {"markets": []}
    assert calls["count"] == 2
