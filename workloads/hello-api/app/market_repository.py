"""PostgreSQL repository for shared market snapshots and worker health."""

from __future__ import annotations

import os
from datetime import datetime, timezone
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
