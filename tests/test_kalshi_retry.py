import json
from urllib.error import URLError

from trading_bot.common import ExecutionMode
from trading_bot.config import AppConfig
from trading_bot.data import kalshi_client as kalshi_module
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

    def _fake_urlopen(request, timeout=10):
        calls["count"] += 1
        if calls["count"] == 1:
            raise URLError("temporary")
        return _FakeResponse({"markets": []})

    monkeypatch.setattr(kalshi_module, "urlopen", _fake_urlopen)

    payload = client.fetch_markets(limit=1)
    assert payload == {"markets": []}
    assert calls["count"] == 2
