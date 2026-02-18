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


def test_parse_market_descriptor_uses_liquidity_fields() -> None:
    raw = {"ticker": "ABC-123", "liquidity": "250.5", "category": "crypto"}
    descriptor = KalshiDataClient._parse_market_descriptor(raw)
    assert descriptor is not None
    assert descriptor.ticker == "ABC-123"
    assert descriptor.liquidity_score == 250.5
    assert descriptor.category == "crypto"


def test_discover_open_markets_filters_by_liquidity() -> None:
    config = AppConfig()
    config.execution.mode = ExecutionMode.PAPER
    guard = SafetyGuard(config)
    client = KalshiDataClient(config.kalshi_base_url, guard)

    payload = {
        "markets": [
            {"ticker": "HIGH-1", "liquidity": 1000},
            {"ticker": "LOW-1", "liquidity": 1},
        ],
        "cursor": None,
    }
    client.fetch_markets = lambda limit, status, cursor=None: payload  # type: ignore[assignment]

    markets = client.discover_open_markets(limit=10, pool_limit=10, min_liquidity=50)
    tickers = [market.ticker for market in markets]
    assert tickers == ["HIGH-1"]
