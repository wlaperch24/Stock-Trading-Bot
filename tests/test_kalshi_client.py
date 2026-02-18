from trading_bot.common import ExecutionMode
from trading_bot.config import AppConfig
from trading_bot.data.kalshi_client import KalshiDataClient
from trading_bot.execution import SafetyGuard


def test_extracts_nested_orderbook_shape() -> None:
    config = AppConfig()
    config.execution.mode = ExecutionMode.PAPER
    guard = SafetyGuard(config)
    client = KalshiDataClient(config.kalshi_base_url, guard)

    raw = {
        "orderbook": {
            "yes": [[48, 100], [49, 200]],
            "no": [[49, 100], [50, 200]],
        }
    }

    yes = client._best_ask(client._extract_side_levels(raw, "yes"))
    no = client._best_ask(client._extract_side_levels(raw, "no"))

    assert yes.price == 0.48
    assert no.price == 0.49


def test_parse_level_handles_bad_payloads() -> None:
    price, size = KalshiDataClient._parse_level({"price": "bad", "size": 10})
    assert price == 0.0
    assert size == 0.0
