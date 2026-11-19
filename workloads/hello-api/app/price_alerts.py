"""Persistent price alerts evaluated against stored Kraken snapshots."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from app.market_repository import MarketDataNotReady, MarketDataRepository

AlertCondition = Literal["above", "below", "percent_up", "percent_down"]
PAIR_PATTERN = re.compile(r"^[A-Za-z0-9]{5,12}$")


class PriceAlertNotFound(Exception):
    """Raised when an alert does not exist."""


class PriceAlertConflict(Exception):
    """Raised when an alert cannot transition from its current state."""


class PriceAlertRepository(MarketDataRepository):
    """PostgreSQL repository for user-managed alert rules and trigger history."""

    def _ensure_schema(self, connection: Any) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS market_price_alerts (
                id BIGSERIAL PRIMARY KEY,
                provider VARCHAR(32) NOT NULL DEFAULT 'kraken',
                pair VARCHAR(16) NOT NULL,
                condition VARCHAR(24) NOT NULL
                    CHECK (condition IN ('above', 'below', 'percent_up', 'percent_down')),
                threshold NUMERIC(28, 12) NOT NULL CHECK (threshold > 0),
                reference_price NUMERIC(28, 12) NOT NULL CHECK (reference_price > 0),
                status VARCHAR(16) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'paused', 'triggered', 'deleted')),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                last_evaluated_at TIMESTAMPTZ,
                triggered_at TIMESTAMPTZ
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_market_price_alerts_active
            ON market_price_alerts (provider, pair, status, created_at DESC)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS market_price_alert_events (
                id BIGSERIAL PRIMARY KEY,
                alert_id BIGINT REFERENCES market_price_alerts(id) ON DELETE SET NULL,
                provider VARCHAR(32) NOT NULL,
                pair VARCHAR(16) NOT NULL,
                condition VARCHAR(24) NOT NULL,
                threshold NUMERIC(28, 12) NOT NULL,
                reference_price NUMERIC(28, 12) NOT NULL,
                observed_price NUMERIC(28, 12) NOT NULL,
                triggered_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_market_price_alert_events_recent
            ON market_price_alert_events (triggered_at DESC, id DESC)
            """
        )

    @staticmethod
    def _alert_payload(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "provider": row["provider"],
            "pair": row["pair"],
            "condition": row["condition"],
            "threshold": float(row["threshold"]),
            "reference_price": float(row["reference_price"]),
            "status": row["status"],
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
            "last_evaluated_at": (
                row["last_evaluated_at"].isoformat()
                if row.get("last_evaluated_at") else None
            ),
            "triggered_at": (
                row["triggered_at"].isoformat()
                if row.get("triggered_at") else None
            ),
        }

    @staticmethod
    def _event_payload(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "alert_id": int(row["alert_id"]) if row["alert_id"] is not None else None,
            "provider": row["provider"],
            "pair": row["pair"],
            "condition": row["condition"],
            "threshold": float(row["threshold"]),
            "reference_price": float(row["reference_price"]),
            "observed_price": float(row["observed_price"]),
            "triggered_at": row["triggered_at"].isoformat(),
        }

    def create_alert(
        self,
        *,
        pair: str,
        condition: AlertCondition,
        threshold: float,
    ) -> dict[str, Any]:
        normalized_pair = pair.strip().upper()
        if not PAIR_PATTERN.fullmatch(normalized_pair):
            raise ValueError("pair must contain 5-12 alphanumeric characters")
        if condition not in {"above", "below", "percent_up", "percent_down"}:
            raise ValueError("Unsupported alert condition")
        value = Decimal(str(threshold))
        if not value.is_finite() or value <= 0:
            raise ValueError("threshold must be a positive finite number")
        if condition == "percent_down" and value >= 100:
            raise ValueError("percent_down threshold must be below 100")

        with self._connect() as connection:
            self._ensure_schema(connection)
            snapshot = connection.execute(
                """
                SELECT last_price
                FROM market_ticker_snapshots
                WHERE provider = 'kraken' AND pair = %s
                ORDER BY fetched_at DESC, id DESC
                LIMIT 1
                """,
                (normalized_pair,),
            ).fetchone()
            if snapshot is None:
                raise MarketDataNotReady(
                    "A stored market snapshot is required to create a price alert"
                )
            reference_price = Decimal(str(snapshot["last_price"]))
            row = connection.execute(
                """
                INSERT INTO market_price_alerts (
                    provider, pair, condition, threshold, reference_price, status
                )
                VALUES ('kraken', %s, %s, %s, %s, 'active')
                RETURNING id, provider, pair, condition, threshold,
                          reference_price, status, created_at, updated_at,
                          last_evaluated_at, triggered_at
                """,
                (normalized_pair, condition, value, reference_price),
            ).fetchone()
        return self._alert_payload(row)

    def list_alerts(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                """
                SELECT id, provider, pair, condition, threshold, reference_price,
                       status, created_at, updated_at, last_evaluated_at, triggered_at
                FROM market_price_alerts
                WHERE status <> 'deleted'
                ORDER BY
                    CASE status WHEN 'active' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END,
                    created_at DESC, id DESC
                """
            ).fetchall()
        return [self._alert_payload(row) for row in rows]

    def list_events(self, limit: int = 50) -> list[dict[str, Any]]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        with self._connect() as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                """
                SELECT id, alert_id, provider, pair, condition, threshold,
                       reference_price, observed_price, triggered_at
                FROM market_price_alert_events
                ORDER BY triggered_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [self._event_payload(row) for row in rows]

    def set_alert_active(self, alert_id: int, is_active: bool) -> dict[str, Any]:
        target_status = "active" if is_active else "paused"
        with self._connect() as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                """
                UPDATE market_price_alerts
                SET status = %s, updated_at = now()
                WHERE id = %s AND status IN ('active', 'paused')
                RETURNING id, provider, pair, condition, threshold,
                          reference_price, status, created_at, updated_at,
                          last_evaluated_at, triggered_at
                """,
                (target_status, alert_id),
            ).fetchone()
            if row is None:
                existing = connection.execute(
                    "SELECT status FROM market_price_alerts WHERE id = %s",
                    (alert_id,),
                ).fetchone()
                if existing is None or existing["status"] == "deleted":
                    raise PriceAlertNotFound
                raise PriceAlertConflict(
                    "A triggered alert cannot be resumed; create a new rule"
                )
        return self._alert_payload(row)

    def delete_alert(self, alert_id: int) -> None:
        with self._connect() as connection:
            self._ensure_schema(connection)
            row = connection.execute(
                """
                UPDATE market_price_alerts
                SET status = 'deleted', updated_at = now()
                WHERE id = %s AND status <> 'deleted'
                RETURNING id
                """,
                (alert_id,),
            ).fetchone()
            if row is None:
                existing = connection.execute(
                    "SELECT id FROM market_price_alerts WHERE id = %s",
                    (alert_id,),
                ).fetchone()
                if existing is None:
                    raise PriceAlertNotFound

    @staticmethod
    def _is_triggered(
        condition: str,
        threshold: Decimal,
        reference_price: Decimal,
        current_price: Decimal,
    ) -> bool:
        if condition == "above":
            return current_price >= threshold
        if condition == "below":
            return current_price <= threshold
        if condition == "percent_up":
            target = reference_price * (Decimal("1") + threshold / Decimal("100"))
            return current_price >= target
        if condition == "percent_down":
            target = reference_price * (Decimal("1") - threshold / Decimal("100"))
            return current_price <= target
        return False

    def evaluate_snapshot(self, snapshot: dict[str, object]) -> int:
        """Evaluate active rules once after each successfully stored snapshot."""
        provider = str(snapshot.get("provider", "kraken"))
        pair = str(snapshot["pair"]).strip().upper()
        current_price = Decimal(str(snapshot["last_price"]))
        fetched_at = datetime.fromisoformat(
            str(snapshot["retrieved_at"]).replace("Z", "+00:00")
        )
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)

        triggered_count = 0
        with self._connect() as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                """
                SELECT id, condition, threshold, reference_price
                FROM market_price_alerts
                WHERE provider = %s AND pair = %s AND status = 'active'
                FOR UPDATE
                """,
                (provider, pair),
            ).fetchall()

            for row in rows:
                threshold = Decimal(str(row["threshold"]))
                reference = Decimal(str(row["reference_price"]))
                matched = self._is_triggered(
                    row["condition"], threshold, reference, current_price
                )
                if matched:
                    connection.execute(
                        """
                        INSERT INTO market_price_alert_events (
                            alert_id, provider, pair, condition, threshold,
                            reference_price, observed_price, triggered_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            row["id"], provider, pair, row["condition"],
                            threshold, reference, current_price, fetched_at,
                        ),
                    )
                    connection.execute(
                        """
                        UPDATE market_price_alerts
                        SET status = 'triggered', triggered_at = %s,
                            last_evaluated_at = %s, updated_at = now()
                        WHERE id = %s AND status = 'active'
                        """,
                        (fetched_at, fetched_at, row["id"]),
                    )
                    triggered_count += 1
                else:
                    connection.execute(
                        """
                        UPDATE market_price_alerts
                        SET last_evaluated_at = %s
                        WHERE id = %s AND status = 'active'
                        """,
                        (fetched_at, row["id"]),
                    )
        return triggered_count
