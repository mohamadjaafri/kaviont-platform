from datetime import datetime, timezone
from decimal import Decimal

from app.price_alerts import PriceAlertRepository


class FakeResult:
    def __init__(self, *, rows=None, row=None):
        self.rows = rows or []
        self.row = row

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, *, rows=None):
        self.rows = rows or []
        self.statements = []
        self.params = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.statements.append(query)
        self.params.append(params)
        if "SELECT id, condition, threshold, reference_price" in query:
            return FakeResult(rows=self.rows)
        return FakeResult()


def test_absolute_alert_thresholds() -> None:
    assert PriceAlertRepository._is_triggered(
        "above", Decimal("70000"), Decimal("65000"), Decimal("70000")
    )
    assert not PriceAlertRepository._is_triggered(
        "above", Decimal("70000"), Decimal("65000"), Decimal("69999")
    )
    assert PriceAlertRepository._is_triggered(
        "below", Decimal("60000"), Decimal("65000"), Decimal("60000")
    )
    assert not PriceAlertRepository._is_triggered(
        "below", Decimal("60000"), Decimal("65000"), Decimal("60001")
    )


def test_percentage_alerts_use_creation_reference_price() -> None:
    reference = Decimal("65000")
    assert PriceAlertRepository._is_triggered(
        "percent_up", Decimal("3"), reference, Decimal("66950")
    )
    assert not PriceAlertRepository._is_triggered(
        "percent_up", Decimal("3"), reference, Decimal("66949")
    )
    assert PriceAlertRepository._is_triggered(
        "percent_down", Decimal("3"), reference, Decimal("63050")
    )
    assert not PriceAlertRepository._is_triggered(
        "percent_down", Decimal("3"), reference, Decimal("63051")
    )


def test_evaluate_snapshot_records_event_and_marks_alert_triggered(monkeypatch) -> None:
    connection = FakeConnection(
        rows=[
            {
                "id": 7,
                "condition": "above",
                "threshold": Decimal("70000"),
                "reference_price": Decimal("65000"),
            },
            {
                "id": 8,
                "condition": "below",
                "threshold": Decimal("60000"),
                "reference_price": Decimal("65000"),
            },
        ]
    )
    repository = PriceAlertRepository("postgresql://test")
    monkeypatch.setattr(repository, "_connect", lambda: connection)

    triggered = repository.evaluate_snapshot(
        {
            "provider": "kraken",
            "pair": "XBTUSD",
            "last_price": 71000,
            "retrieved_at": "2026-11-19T09:00:00+00:00",
        }
    )

    assert triggered == 1
    statements = "\n".join(connection.statements)
    assert "INSERT INTO market_price_alert_events" in statements
    assert "SET status = 'triggered'" in statements
    assert "SET last_evaluated_at" in statements


def test_create_alert_rejects_invalid_pair_and_percent_drop() -> None:
    repository = PriceAlertRepository("postgresql://test")

    try:
        repository.create_alert(pair="BTC/USD", condition="above", threshold=70000)
    except ValueError as exc:
        assert "pair" in str(exc)
    else:
        raise AssertionError("Invalid pair must be rejected")

    try:
        repository.create_alert(
            pair="XBTUSD", condition="percent_down", threshold=100
        )
    except ValueError as exc:
        assert "below 100" in str(exc)
    else:
        raise AssertionError("A percentage drop of 100% or more must be rejected")
