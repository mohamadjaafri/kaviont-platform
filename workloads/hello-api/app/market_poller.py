"""Periodic background polling and in-memory cache for Kraken market data."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from time import monotonic

from app.financial import FinancialDataProviderError, fetch_kraken_ticker

logger = logging.getLogger(__name__)

TickerFetcher = Callable[[str], Awaitable[dict[str, object]]]
PAIR_PATTERN = re.compile(r"^[A-Za-z0-9]{5,12}$")


class MarketDataNotReady(Exception):
    """Raised until the poller has stored its first successful market-data snapshot."""


class KrakenTickerPoller:
    """Fetch a ticker on startup and refresh it on a fixed interval."""

    def __init__(
        self,
        *,
        pair: str = "XBTUSD",
        interval_seconds: float = 60.0,
        enabled: bool = True,
        fetcher: TickerFetcher = fetch_kraken_ticker,
    ) -> None:
        normalized_pair = pair.strip().upper()
        if not PAIR_PATTERN.fullmatch(normalized_pair):
            raise ValueError("KRAKEN_MARKET_PAIR must be 5-12 alphanumeric characters")
        if interval_seconds < 1:
            raise ValueError("KRAKEN_POLL_INTERVAL_SECONDS must be at least 1")
        self.pair = normalized_pair
        self.interval_seconds = interval_seconds
        self.enabled = enabled
        self._fetcher = fetcher
        self._snapshot: dict[str, object] | None = None
        self._last_success_at: datetime | None = None
        self._last_success_monotonic: float | None = None
        self._last_attempt_at: datetime | None = None
        self._last_error: str | None = None
        self._stop_event: asyncio.Event | None = None
        self._task: asyncio.Task[None] | None = None

    @classmethod
    def from_environment(cls) -> "KrakenTickerPoller":
        enabled_value = os.getenv("KRAKEN_POLLING_ENABLED", "true").strip().lower()
        enabled = enabled_value in {"1", "true", "yes", "on"}
        interval = float(os.getenv("KRAKEN_POLL_INTERVAL_SECONDS", "60"))
        pair = os.getenv("KRAKEN_MARKET_PAIR", "XBTUSD")
        return cls(pair=pair, interval_seconds=interval, enabled=enabled)

    async def start(self) -> None:
        """Perform an initial refresh, then schedule periodic refreshes."""
        if not self.enabled or self.running:
            return
        await self.refresh()
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(
            self._run(),
            name="kaviont-kraken-market-data-poller",
        )

    async def stop(self) -> None:
        """Stop the periodic task cleanly during application shutdown."""
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None:
            await self._task
        self._task = None
        self._stop_event = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def refresh(self) -> bool:
        """Fetch one snapshot and retain the previous good value on failure."""
        self._last_attempt_at = datetime.now(timezone.utc)
        try:
            snapshot = await self._fetcher(self.pair)
        except FinancialDataProviderError as exc:
            self._last_error = (
                "timeout" if type(exc).__name__ == "FinancialDataTimeoutError"
                else "provider_error"
            )
            logger.warning("Kraken market-data refresh failed: %s", self._last_error)
            return False
        except Exception:
            self._last_error = "unexpected_error"
            logger.exception("Unexpected error while refreshing Kraken market data")
            return False

        self._snapshot = snapshot
        self._last_success_at = datetime.now(timezone.utc)
        self._last_success_monotonic = monotonic()
        self._last_error = None
        return True

    async def _run(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.interval_seconds,
                )
            except asyncio.TimeoutError:
                await self.refresh()

    def _cache_age_seconds(self) -> float | None:
        if self._last_success_monotonic is None:
            return None
        return max(0.0, monotonic() - self._last_success_monotonic)

    def get_snapshot(self) -> dict[str, object]:
        """Return the latest cached ticker and freshness metadata."""
        if self._snapshot is None:
            raise MarketDataNotReady("No successful Kraken snapshot is available yet")
        age = self._cache_age_seconds()
        return {
            **self._snapshot,
            "cache_age_seconds": round(age or 0.0, 1),
            "stale": age is not None and age > self.interval_seconds * 2,
            "poll_interval_seconds": self.interval_seconds,
        }

    def status(self) -> dict[str, object]:
        """Return safe poller status without exposing provider internals."""
        age = self._cache_age_seconds()
        return {
            "provider": "kraken",
            "pair": self.pair,
            "polling_enabled": self.enabled,
            "poll_interval_seconds": self.interval_seconds,
            "has_snapshot": self._snapshot is not None,
            "cache_age_seconds": round(age, 1) if age is not None else None,
            "stale": age is not None and age > self.interval_seconds * 2,
            "last_attempt_at": (
                self._last_attempt_at.isoformat() if self._last_attempt_at else None
            ),
            "last_successful_update": (
                self._last_success_at.isoformat() if self._last_success_at else None
            ),
            "last_error": self._last_error,
            "running": self.running,
        }
