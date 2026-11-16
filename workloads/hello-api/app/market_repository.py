"""PostgreSQL repository for shared market snapshots and worker health."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

WORKER_LOCK_ID = 734_119_208_081


class MarketDataNotReady(Exception):
    """Raised when no successful market-data snapshot exists yet."""


class MarketDataStorageNotConfigured(Exception):
    """Raised when the market-data database connection is not configured."""


class MarketDataRepository:
    """Small PostgreSQL repository shared by the API and the market-data worker."""

    def __init__(self, database_url: str) -> None:
        if not database_url.strip():
            raise MarketDataStorageNotConfigured(
                "Set DATABASE_URL to enable the market-data API"
            )
        self.database_url = database_url

    @classmethod
    def from_environment(cls) -> "MarketDataRepository":
        return cls(os.getenv("DATABASE_URL", "").strip())

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(
            self.database_url,
            connect_timeout=3,
            row_factory=dict_row,
        )

    def try_acquire_worker_lock(self) -> psycopg.Connection | None:
        """Hold a session-level advisory lock for the worker process lifetime."""
        connection = psycopg.connect(
            self.database_url,
            connect_timeout=3,
            autocommit=True,
            row_factory=dict_row,
        )
        try:
            result = connection.execute(
                "SELECT pg_try_advisory_lock(%s) AS acquired",
                (WORKER_LOCK_ID,),
            ).fetchone()
            if not result or not result["acquired"]:
                connection.close()
                return None
            return connection
        except Exception:
            connection.close()
            raise

    def release_worker_lock(self, connection: psycopg.Connection) -> None:
        try:
            connection.execute(
                "SELECT pg_advisory_unlock(%s)",
                (WORKER_LOCK_ID,),
            )
        finally:
            connection.close()

    def record_attempt(self, pair: str, worker_instance: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO market_data_worker_state (
                    provider, pair, last_attempt_at, worker_status,
                    worker_instance, heartbeat_at
                )
                VALUES ('kraken', %s, now(), 'running', %s, now())
                ON CONFLICT (provider, pair) DO UPDATE SET
                    last_attempt_at = now(),
                    worker_status = 'running',
                    worker_instance = EXCLUDED.worker_instance,
                    heartbeat_at = now()
                """,
                (pair, worker_instance),
            )

    def record_failure(
        self,
        pair: str,
        worker_instance: str,
        error_category: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO market_data_worker_state (
                    provider, pair, last_attempt_at, last_error,
                    worker_status, worker_instance, heartbeat_at
                )
                VALUES ('kraken', %s, now(), %s, 'running', %s, now())
                ON CONFLICT (provider, pair) DO UPDATE SET
                    last_error = EXCLUDED.last_error,
                    worker_status = 'running',
                    worker_instance = EXCLUDED.worker_instance,
                    heartbeat_at = now()
                """,
                (pair, error_category, worker_instance),
            )

    def save_snapshot(
        self,
        snapshot: dict[str, object],
        worker_instance: str,
    ) -> None:
        provider = str(snapshot["provider"])
        pair = str(snapshot["pair"])
        fetched_at = datetime.fromisoformat(
            str(snapshot["retrieved_at"]).replace("Z", "+00:00")
        )
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO market_ticker_snapshots (
                    provider, pair, last_price, bid, ask, volume_24h,
                    high_24h, low_24h, fetched_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    provider,
                    pair,
                    snapshot["last_price"],
                    snapshot["bid"],
                    snapshot["ask"],
                    snapshot["volume_24h"],
                    snapshot["high_24h"],
                    snapshot["low_24h"],
                    fetched_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO market_data_worker_state (
                    provider, pair, last_attempt_at, last_successful_update,
                    last_error, worker_status, worker_instance, heartbeat_at
                )
                VALUES (%s, %s, now(), now(), NULL, 'running', %s, now())
                ON CONFLICT (provider, pair) DO UPDATE SET
                    last_attempt_at = now(),
                    last_successful_update = now(),
                    last_error = NULL,
                    worker_status = 'running',
                    worker_instance = EXCLUDED.worker_instance,
                    heartbeat_at = now()
                """,
                (provider, pair, worker_instance),
            )

    def mark_stopped(self, pair: str, worker_instance: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE market_data_worker_state
                SET worker_status = 'stopped',
                    worker_instance = %s,
                    heartbeat_at = now()
                WHERE provider = 'kraken' AND pair = %s AND worker_instance = %s
                """,
                (worker_instance, pair, worker_instance),
            )

    def latest_snapshot(
        self,
        pair: str,
        poll_interval_seconds: int,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT provider, pair, last_price, bid, ask, volume_24h,
                       high_24h, low_24h, fetched_at,
                       EXTRACT(EPOCH FROM (now() - fetched_at))::double precision
                           AS cache_age_seconds
                FROM market_ticker_snapshots
                WHERE provider = 'kraken' AND pair = %s
                ORDER BY fetched_at DESC, id DESC
                LIMIT 1
                """,
                (pair,),
            ).fetchone()

        if row is None:
            raise MarketDataNotReady("No market-data snapshot has been stored yet")

        age = max(0.0, float(row["cache_age_seconds"] or 0.0))
        result: dict[str, Any] = {
            key: float(row[key])
            for key in (
                "last_price", "bid", "ask", "volume_24h", "high_24h", "low_24h"
            )
        }
        result.update(
            {
                "provider": row["provider"],
                "pair": row["pair"],
                # This is Kaviont's fetch time, not an exchange event timestamp.
                "retrieved_at": row["fetched_at"].isoformat(),
                "fetched_at": row["fetched_at"].isoformat(),
                "cache_age_seconds": round(age, 1),
                "stale": age > poll_interval_seconds * 2,
                "poll_interval_seconds": poll_interval_seconds,
            }
        )
        return result


    def latest_tickers(self, poll_interval_seconds: int) -> dict[str, Any]:
        """Return the newest stored snapshot for every tracked Kraken pair."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT ON (provider, pair)
                       provider, pair, last_price, bid, ask, volume_24h,
                       high_24h, low_24h, fetched_at,
                       EXTRACT(EPOCH FROM (now() - fetched_at))::double precision
                           AS cache_age_seconds
                FROM market_ticker_snapshots
                WHERE provider = 'kraken'
                ORDER BY provider, pair, fetched_at DESC, id DESC
                """
            ).fetchall()

        tickers: list[dict[str, Any]] = []
        for row in rows:
            age = max(0.0, float(row["cache_age_seconds"] or 0.0))
            tickers.append(
                {
                    "provider": row["provider"],
                    "pair": row["pair"],
                    "last_price": float(row["last_price"]),
                    "bid": float(row["bid"]),
                    "ask": float(row["ask"]),
                    "volume_24h": float(row["volume_24h"]),
                    "high_24h": float(row["high_24h"]),
                    "low_24h": float(row["low_24h"]),
                    "fetched_at": row["fetched_at"].isoformat(),
                    "cache_age_seconds": round(age, 1),
                    "stale": age > poll_interval_seconds * 2,
                }
            )

        return {
            "provider": "kraken",
            "count": len(tickers),
            "poll_interval_seconds": poll_interval_seconds,
            "tickers": tickers,
        }

    def historical_ticker(
        self,
        pair: str,
        time_range: str,
        limit: int = 500,
    ) -> dict[str, Any]:
        """Return a chronological and evenly downsampled historical time series."""
        durations = {
            "1h": timedelta(hours=1),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7),
        }
        if time_range not in durations:
            raise ValueError("time_range must be one of: 1h, 24h, 7d")
        if not 2 <= limit <= 2000:
            raise ValueError("limit must be between 2 and 2000")

        window_end = datetime.now(timezone.utc)
        window_start = window_end - durations[time_range]
        with self._connect() as connection:
            rows = connection.execute(
                """
                WITH ranged AS (
                    SELECT id, provider, pair, last_price, bid, ask,
                           volume_24h, high_24h, low_24h, fetched_at
                    FROM market_ticker_snapshots
                    WHERE provider = 'kraken'
                      AND pair = %s
                      AND fetched_at >= %s
                ),
                ranked AS (
                    SELECT *,
                           count(*) OVER () AS total_points,
                           ntile(GREATEST(%s - 1, 1))
                               OVER (ORDER BY fetched_at, id) AS bucket
                    FROM ranged
                ),
                sampled AS (
                    SELECT DISTINCT ON (bucket)
                           id, provider, pair, last_price, bid, ask,
                           volume_24h, high_24h, low_24h, fetched_at,
                           total_points
                    FROM ranked
                    ORDER BY bucket, fetched_at DESC, id DESC
                ),
                first_point AS (
                    SELECT id, provider, pair, last_price, bid, ask,
                           volume_24h, high_24h, low_24h, fetched_at,
                           total_points
                    FROM ranked
                    ORDER BY fetched_at, id
                    LIMIT 1
                ),
                selected AS (
                    SELECT * FROM sampled
                    UNION
                    SELECT * FROM first_point
                )
                SELECT id, provider, pair, last_price, bid, ask,
                       volume_24h, high_24h, low_24h, fetched_at,
                       total_points
                FROM selected
                ORDER BY fetched_at ASC, id ASC
                """,
                (pair, window_start, limit),
            ).fetchall()

        total_points = int(rows[0]["total_points"]) if rows else 0
        data = [
            {
                "timestamp": row["fetched_at"].isoformat(),
                "price": float(row["last_price"]),
                "bid": float(row["bid"]),
                "ask": float(row["ask"]),
                "volume_24h": float(row["volume_24h"]),
                "high_24h": float(row["high_24h"]),
                "low_24h": float(row["low_24h"]),
            }
            for row in rows
        ]
        return {
            "provider": "kraken",
            "pair": pair,
            "range": time_range,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "total_points": total_points,
            "returned_points": len(data),
            "limit": limit,
            "downsampled": total_points > len(data),
            "data": data,
        }

    def market_summary(self, pair: str, time_range: str) -> dict[str, Any]:
        """Calculate price change and descriptive statistics for a time window."""
        durations = {
            "1h": timedelta(hours=1),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7),
        }
        if time_range not in durations:
            raise ValueError("time_range must be one of: 1h, 24h, 7d")

        window_end = datetime.now(timezone.utc)
        window_start = window_end - durations[time_range]
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    count(*) AS sample_count,
                    (array_agg(last_price ORDER BY fetched_at ASC, id ASC))[1]
                        AS first_price,
                    (array_agg(last_price ORDER BY fetched_at DESC, id DESC))[1]
                        AS latest_price,
                    min(last_price) AS low_price,
                    max(last_price) AS high_price,
                    avg(last_price) AS average_price,
                    min(fetched_at) AS first_fetched_at,
                    max(fetched_at) AS last_fetched_at
                FROM market_ticker_snapshots
                WHERE provider = 'kraken'
                  AND pair = %s
                  AND fetched_at >= %s
                """,
                (pair, window_start),
            ).fetchone()

        sample_count = int(row["sample_count"] or 0)
        first_price = float(row["first_price"]) if row["first_price"] is not None else None
        latest_price = float(row["latest_price"]) if row["latest_price"] is not None else None
        absolute_change = (
            latest_price - first_price
            if first_price is not None and latest_price is not None
            else None
        )
        percent_change = (
            (absolute_change / first_price) * 100.0
            if absolute_change is not None and first_price
            else None
        )

        return {
            "provider": "kraken",
            "pair": pair,
            "range": time_range,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "sample_count": sample_count,
            "first_price": first_price,
            "latest_price": latest_price,
            "price_change_absolute": absolute_change,
            "price_change_percent": percent_change,
            "low_price": float(row["low_price"]) if row["low_price"] is not None else None,
            "high_price": float(row["high_price"]) if row["high_price"] is not None else None,
            "average_price": float(row["average_price"]) if row["average_price"] is not None else None,
            "first_fetched_at": (
                row["first_fetched_at"].isoformat()
                if row["first_fetched_at"] else None
            ),
            "last_fetched_at": (
                row["last_fetched_at"].isoformat()
                if row["last_fetched_at"] else None
            ),
        }

    def worker_status(
        self,
        pair: str,
        poll_interval_seconds: int,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT provider, pair, last_attempt_at, last_successful_update,
                       last_error, worker_status, worker_instance,
                       EXTRACT(EPOCH FROM (now() - heartbeat_at))::double precision
                           AS heartbeat_age_seconds
                FROM market_data_worker_state
                WHERE provider = 'kraken' AND pair = %s
                """,
                (pair,),
            ).fetchone()

        if row is None:
            return {
                "provider": "kraken",
                "pair": pair,
                "polling_enabled": True,
                "poll_interval_seconds": poll_interval_seconds,
                "worker_status": "not_started",
                "running": False,
                "has_snapshot": False,
                "last_attempt_at": None,
                "last_successful_update": None,
                "last_error": None,
                "worker_instance": None,
                "heartbeat_age_seconds": None,
            }

        heartbeat_age = (
            max(0.0, float(row["heartbeat_age_seconds"]))
            if row["heartbeat_age_seconds"] is not None
            else None
        )
        running = (
            row["worker_status"] == "running"
            and heartbeat_age is not None
            and heartbeat_age <= max(180, poll_interval_seconds * 3)
        )
        return {
            "provider": row["provider"],
            "pair": row["pair"],
            "polling_enabled": True,
            "poll_interval_seconds": poll_interval_seconds,
            "worker_status": (
                "running" if running
                else "stopped" if row["worker_status"] == "stopped"
                else "unhealthy"
            ),
            "running": running,
            "has_snapshot": row["last_successful_update"] is not None,
            "last_attempt_at": (
                row["last_attempt_at"].isoformat()
                if row["last_attempt_at"] else None
            ),
            "last_successful_update": (
                row["last_successful_update"].isoformat()
                if row["last_successful_update"] else None
            ),
            "last_error": row["last_error"],
            "worker_instance": row["worker_instance"],
            "heartbeat_age_seconds": (
                round(heartbeat_age, 1) if heartbeat_age is not None else None
            ),
        }
