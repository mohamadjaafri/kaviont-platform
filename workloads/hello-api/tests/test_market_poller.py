import asyncio

from app.financial import FinancialDataProviderError
from app.market_poller import KrakenTickerPoller, MarketDataNotReady


def run(coro):
    return asyncio.run(coro)


def sample_ticker(pair: str) -> dict[str, object]:
    return {
        "provider": "kraken",
        "pair": pair,
        "last_price": 65000.0,
        "bid": 64999.0,
        "ask": 65001.0,
        "volume_24h": 123.4,
        "high_24h": 66000.0,
        "low_24h": 64000.0,
        "retrieved_at": "2026-11-16T12:00:00+00:00",
    }


def test_poller_refreshes_and_serves_cached_snapshot() -> None:
    calls = []

    async def fetcher(pair: str) -> dict[str, object]:
        calls.append(pair)
        return sample_ticker(pair)

    async def scenario():
        poller = KrakenTickerPoller(fetcher=fetcher)
        assert await poller.refresh() is True
        return poller.get_snapshot(), poller.status()

    snapshot, status = run(scenario())

    assert calls == ["XBTUSD"]
    assert snapshot["last_price"] == 65000.0
    assert snapshot["stale"] is False
    assert status["has_snapshot"] is True
    assert status["last_error"] is None


def test_poller_keeps_last_good_snapshot_when_provider_fails() -> None:
    calls = 0

    async def fetcher(pair: str) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return sample_ticker(pair)
        raise FinancialDataProviderError("provider unavailable")

    async def scenario():
        poller = KrakenTickerPoller(fetcher=fetcher)
        assert await poller.refresh() is True
        assert await poller.refresh() is False
        return poller.get_snapshot(), poller.status()

    snapshot, status = run(scenario())

    assert calls == 2
    assert snapshot["last_price"] == 65000.0
    assert status["has_snapshot"] is True
    assert status["last_error"] == "provider_error"


def test_poller_starts_immediately_and_stops_cleanly() -> None:
    calls = []

    async def fetcher(pair: str) -> dict[str, object]:
        calls.append(pair)
        return sample_ticker(pair)

    async def scenario():
        poller = KrakenTickerPoller(interval_seconds=1.0, fetcher=fetcher)
        await poller.start()
        assert poller.running is True
        await asyncio.sleep(1.05)
        await poller.stop()
        assert poller.running is False
        return len(calls)

    count = run(scenario())

    assert count >= 2


def test_disabled_poller_does_not_fetch() -> None:
    calls = []

    async def fetcher(pair: str) -> dict[str, object]:
        calls.append(pair)
        return sample_ticker(pair)

    async def scenario():
        poller = KrakenTickerPoller(enabled=False, fetcher=fetcher)
        await poller.start()
        status = poller.status()
        await poller.stop()
        return status

    status = run(scenario())

    assert calls == []
    assert status["polling_enabled"] is False
    assert status["running"] is False


def test_snapshot_requires_first_successful_poll() -> None:
    poller = KrakenTickerPoller()
    try:
        poller.get_snapshot()
    except MarketDataNotReady:
        return
    raise AssertionError("Expected MarketDataNotReady")
