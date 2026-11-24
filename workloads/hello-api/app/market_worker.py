"""Dedicated process that polls Kraken and stores snapshots in PostgreSQL."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import signal
import socket
import uuid
from collections.abc import Awaitable, Callable

import psycopg

from app.financial import (
    FinancialDataProviderError,
    FinancialDataTimeoutError,
    fetch_kraken_ticker,
)
from app.market_repository import MarketDataRepository
from app.observability import configure_worker_observability
from app.price_alerts import PriceAlertRepository

logger = logging.getLogger("kaviont.market-data-worker")
TickerFetcher = Callable[[str], Awaitable[dict[str, object]]]
AlertEvaluator = Callable[[dict[str, object]], int]


def _error_category(error: Exception) -> str:
    if isinstance(error, FinancialDataTimeoutError):
        return "timeout"
    if isinstance(error, FinancialDataProviderError):
        return "provider_error"
    return "unexpected_error"


async def poll_once(
    repository: MarketDataRepository,
    *,
    pair: str,
    worker_instance: str,
    fetcher: TickerFetcher = fetch_kraken_ticker,
    alert_evaluator: AlertEvaluator | None = None,
) -> bool:
    """Fetch, persist, then evaluate matching price alerts for one snapshot."""
    repository.record_attempt(pair, worker_instance)
    try:
        snapshot = await fetcher(pair)
    except Exception as exc:
        category = _error_category(exc)
        repository.record_failure(pair, worker_instance, category)
        if isinstance(exc, FinancialDataProviderError):
            logger.warning("Market-data polling failed: %s", category)
        else:
            logger.exception("Unexpected market-data worker error")
        return False

    repository.save_snapshot(snapshot, worker_instance)
    if alert_evaluator is not None:
        alert_evaluator(snapshot)
    return True


async def _wait_for_worker_lock(
    repository: MarketDataRepository,
    stop_event: asyncio.Event,
) -> psycopg.Connection | None:
    """Wait until PostgreSQL grants the singleton worker lock."""
    while not stop_event.is_set():
        try:
            connection = repository.try_acquire_worker_lock()
            if connection is not None:
                return connection
            logger.info("Another market-data worker holds the advisory lock")
        except psycopg.Error:
            logger.exception("PostgreSQL unavailable while acquiring worker lock")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=5)
        except asyncio.TimeoutError:
            continue
    return None


async def run_worker() -> None:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL must be configured for market-data-worker")

    pair = os.getenv("KRAKEN_MARKET_PAIR", "XBTUSD").strip().upper()
    if not re.fullmatch(r"[A-Za-z0-9]{5,12}", pair):
        raise ValueError("KRAKEN_MARKET_PAIR must be 5-12 alphanumeric characters")
    interval_seconds = float(os.getenv("KRAKEN_POLL_INTERVAL_SECONDS", "60"))
    if interval_seconds < 1:
        raise ValueError("KRAKEN_POLL_INTERVAL_SECONDS must be at least 1")

    configure_worker_observability()
    repository = MarketDataRepository(database_url)
    alert_repository = PriceAlertRepository(database_url)
    worker_instance = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for signal_name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signal_name, stop_event.set)

    logger.info(
        "Starting market-data worker for %s with a %s second interval",
        pair,
        interval_seconds,
    )
    lock_connection = await _wait_for_worker_lock(repository, stop_event)
    if lock_connection is None:
        return

    logger.info("PostgreSQL singleton lock acquired")
    try:
        while not stop_event.is_set():
            try:
                lock_connection.execute("SELECT 1")
            except psycopg.Error:
                logger.exception("Worker advisory-lock connection was lost; reacquiring")
                try:
                    lock_connection.close()
                except psycopg.Error:
                    pass
                lock_connection = await _wait_for_worker_lock(repository, stop_event)
                if lock_connection is None:
                    break

            try:
                await poll_once(
                    repository,
                    pair=pair,
                    worker_instance=worker_instance,
                    alert_evaluator=alert_repository.evaluate_snapshot,
                )
            except psycopg.Error:
                logger.exception("Could not persist market-data worker state or evaluate alerts")
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=interval_seconds,
                )
            except asyncio.TimeoutError:
                continue
    finally:
        try:
            repository.mark_stopped(pair, worker_instance)
        except psycopg.Error:
            logger.exception("Could not mark market-data worker as stopped")
        if lock_connection is not None:
            repository.release_worker_lock(lock_connection)
        logger.info("Market-data worker stopped")


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
