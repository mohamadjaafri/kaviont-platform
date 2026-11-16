from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.market_repository import MarketDataRepository


class FakeResult:
    def __init__(self, *, rows=None, row=None):
        self.rows = rows or []
        self.row = row

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, *, rows=None, row=None):
        self.result = FakeResult(rows=rows, row=row)
        self.query = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.params = params
        return self.result


def test_latest_tickers_returns_one_snapshot_per_pair(monkeypatch):
    now = datetime.now(timezone.utc)
    rows = [
        {
            "provider": "kraken",
            "pair": "XBTUSD",
            "last_price": Decimal("65000"),
            "bid": Decimal("64999"),
            "ask": Decimal("65001"),
            "volume_24h": Decimal("12"),
            "high_24h": Decimal("66000"),
            "low_24h": Decimal("64000"),
            "fetched_at": now,
            "cache_age_seconds": 2.0,
        }
    ]
    connection = FakeConnection(rows=rows)
    repository = MarketDataRepository("postgresql://test")
    monkeypatch.setattr(repository, "_connect", lambda: connection)

    result = repository.latest_tickers(60)

    assert "DISTINCT ON (provider, pair)" in connection.query
    assert result["count"] == 1
    assert result["tickers"][0]["pair"] == "XBTUSD"
    assert result["tickers"][0]["last_price"] == 65000.0
    assert result["tickers"][0]["stale"] is False


def test_historical_ticker_returns_chronological_sample_and_total(monkeypatch):
    now = datetime.now(timezone.utc)
    rows = [
        {
            "id": 1,
            "provider": "kraken",
            "pair": "XBTUSD",
            "last_price": Decimal("64000"),
            "bid": Decimal("63999"),
            "ask": Decimal("64001"),
            "volume_24h": Decimal("12"),
            "high_24h": Decimal("65000"),
            "low_24h": Decimal("63000"),
            "fetched_at": now - timedelta(minutes=10),
            "total_points": 120,
        },
        {
            "id": 120,
            "provider": "kraken",
            "pair": "XBTUSD",
            "last_price": Decimal("65000"),
            "bid": Decimal("64999"),
            "ask": Decimal("65001"),
            "volume_24h": Decimal("14"),
            "high_24h": Decimal("66000"),
            "low_24h": Decimal("64000"),
            "fetched_at": now,
            "total_points": 120,
        },
    ]
    connection = FakeConnection(rows=rows)
    repository = MarketDataRepository("postgresql://test")

    monkeypatch.setattr(repository, "_connect", lambda: connection)
    result = repository.historical_ticker("XBTUSD", "24h", 2)

    assert connection.params[0] == "XBTUSD"
    assert connection.params[2] == 2
    assert "ntile" in connection.query.lower()
    assert result["total_points"] == 120
    assert result["returned_points"] == 2
    assert result["downsampled"] is True
    assert result["data"][0]["price"] == 64000.0
    assert result["data"][1]["price"] == 65000.0


def test_historical_ticker_returns_empty_series_without_snapshots(monkeypatch):
    connection = FakeConnection(rows=[])
    repository = MarketDataRepository("postgresql://test")
    monkeypatch.setattr(repository, "_connect", lambda: connection)

    result = repository.historical_ticker("XBTUSD", "7d", 100)

    assert result["total_points"] == 0
    assert result["returned_points"] == 0
    assert result["data"] == []
    assert result["downsampled"] is False


def test_market_summary_calculates_absolute_and_percentage_change(monkeypatch):
    row = {
        "sample_count": 3,
        "first_price": Decimal("40000"),
        "latest_price": Decimal("42000"),
        "low_price": Decimal("39500"),
        "high_price": Decimal("42500"),
        "average_price": Decimal("41000"),
        "first_fetched_at": datetime(2026, 11, 16, 10, tzinfo=timezone.utc),
        "last_fetched_at": datetime(2026, 11, 16, 11, tzinfo=timezone.utc),
    }
    connection = FakeConnection(row=row)
    repository = MarketDataRepository("postgresql://test")
    monkeypatch.setattr(repository, "_connect", lambda: connection)

    result = repository.market_summary("XBTUSD", "1h")

    assert connection.params[0] == "XBTUSD"
    assert result["sample_count"] == 3
    assert result["price_change_absolute"] == 2000.0
    assert result["price_change_percent"] == 5.0
    assert result["average_price"] == 41000.0


def test_market_summary_returns_null_statistics_without_snapshots(monkeypatch):
    row = {
        "sample_count": 0,
        "first_price": None,
        "latest_price": None,
        "low_price": None,
        "high_price": None,
        "average_price": None,
        "first_fetched_at": None,
        "last_fetched_at": None,
    }
    connection = FakeConnection(row=row)
    repository = MarketDataRepository("postgresql://test")
    monkeypatch.setattr(repository, "_connect", lambda: connection)

    result = repository.market_summary("XBTUSD", "24h")

    assert result["sample_count"] == 0
    assert result["first_price"] is None
    assert result["price_change_percent"] is None


def test_history_rejects_invalid_range_or_limit():
    repository = MarketDataRepository("postgresql://test")

    try:
        repository.historical_ticker("XBTUSD", "30d", 100)
    except ValueError as exc:
        assert "time_range" in str(exc)
    else:
        raise AssertionError("Invalid range must be rejected")

    try:
        repository.historical_ticker("XBTUSD", "24h", 1)
    except ValueError as exc:
        assert "limit" in str(exc)
    else:
        raise AssertionError("Invalid limit must be rejected")
