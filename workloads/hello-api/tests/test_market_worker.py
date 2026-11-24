import asyncio

from app.financial import FinancialDataProviderError, FinancialDataTimeoutError
from app.market_worker import poll_once


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


class RecordingRepository:
    def __init__(self):
        self.attempts = []
        self.failures = []
        self.snapshots = []

    def record_attempt(self, pair, worker_instance):
        self.attempts.append((pair, worker_instance))

    def record_failure(self, pair, worker_instance, category):
        self.failures.append((pair, worker_instance, category))

    def save_snapshot(self, snapshot, worker_instance):
        self.snapshots.append((snapshot, worker_instance))


def run(coro):
    return asyncio.run(coro)


def test_worker_persists_successful_snapshot() -> None:
    repository = RecordingRepository()

    async def fetcher(pair: str) -> dict[str, object]:
        return sample_ticker(pair)

    success = run(
        poll_once(
            repository,
            pair="XBTUSD",
            worker_instance="worker-test",
            fetcher=fetcher,
        )
    )

    assert success is True
    assert repository.attempts == [("XBTUSD", "worker-test")]
    assert repository.failures == []
    assert repository.snapshots[0][0]["last_price"] == 65000.0
    assert repository.snapshots[0][1] == "worker-test"


def test_worker_records_provider_failure_without_overwriting_snapshot() -> None:
    repository = RecordingRepository()

    async def fetcher(_pair: str) -> dict[str, object]:
        raise FinancialDataProviderError("provider unavailable")

    success = run(
        poll_once(
            repository,
            pair="XBTUSD",
            worker_instance="worker-test",
            fetcher=fetcher,
        )
    )

    assert success is False
    assert repository.attempts == [("XBTUSD", "worker-test")]
    assert repository.failures == [("XBTUSD", "worker-test", "provider_error")]
    assert repository.snapshots == []


def test_worker_records_timeout_category() -> None:
    repository = RecordingRepository()

    async def fetcher(_pair: str) -> dict[str, object]:
        raise FinancialDataTimeoutError("timeout")

    success = run(
        poll_once(
            repository,
            pair="XBTUSD",
            worker_instance="worker-test",
            fetcher=fetcher,
        )
    )

    assert success is False
    assert repository.failures == [("XBTUSD", "worker-test", "timeout")]


def test_worker_evaluates_alerts_after_persisting_snapshot() -> None:
    events = []

    class OrderedRepository(RecordingRepository):
        def save_snapshot(self, snapshot, worker_instance):
            super().save_snapshot(snapshot, worker_instance)
            events.append("snapshot_saved")

    repository = OrderedRepository()

    async def fetcher(pair: str) -> dict[str, object]:
        return sample_ticker(pair)

    def evaluate_alerts(snapshot):
        events.append(("alerts_evaluated", snapshot["pair"]))
        return 0

    success = run(
        poll_once(
            repository,
            pair="XBTUSD",
            worker_instance="worker-test",
            fetcher=fetcher,
            alert_evaluator=evaluate_alerts,
        )
    )

    assert success is True
    assert events == ["snapshot_saved", ("alerts_evaluated", "XBTUSD")]
