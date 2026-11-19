from fastapi.testclient import TestClient

from app.main import app
from app.price_alerts import PriceAlertConflict, PriceAlertNotFound
from app.market_repository import MarketDataNotReady

client = TestClient(app)


class FakePriceAlertRepository:
    def list_alerts(self):
        return [{"id": 1, "pair": "XBTUSD", "condition": "above", "threshold": 70000, "status": "active"}]

    def list_events(self, limit):
        return [{"id": 2, "pair": "XBTUSD", "observed_price": 71000}][:limit]

    def create_alert(self, **kwargs):
        return {"id": 3, **kwargs, "reference_price": 65000, "status": "active"}

    def set_alert_active(self, alert_id, is_active):
        if alert_id == 404:
            raise PriceAlertNotFound
        if alert_id == 5:
            raise PriceAlertConflict("A triggered alert cannot be resumed")
        return {"id": alert_id, "status": "active" if is_active else "paused"}

    def delete_alert(self, alert_id):
        if alert_id == 404:
            raise PriceAlertNotFound


def test_list_price_alerts(monkeypatch):
    import app.price_alerts_api as api

    monkeypatch.setattr(
        api, "get_price_alert_repository", lambda: FakePriceAlertRepository()
    )
    response = client.get("/v1/market/kraken/alerts")

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["alerts"][0]["pair"] == "XBTUSD"


def test_create_price_alert(monkeypatch):
    import app.price_alerts_api as api

    monkeypatch.setattr(
        api, "get_price_alert_repository", lambda: FakePriceAlertRepository()
    )
    response = client.post(
        "/v1/market/kraken/alerts",
        json={"pair": "XBTUSD", "condition": "above", "threshold": 70000},
    )

    assert response.status_code == 201
    assert response.json()["alert"]["reference_price"] == 65000


def test_create_price_alert_validates_pair_condition_and_percent_drop(monkeypatch):
    import app.price_alerts_api as api

    monkeypatch.setattr(
        api, "get_price_alert_repository", lambda: FakePriceAlertRepository()
    )
    invalid_pair = client.post(
        "/v1/market/kraken/alerts",
        json={"pair": "BTC/USD", "condition": "above", "threshold": 70000},
    )
    invalid_condition = client.post(
        "/v1/market/kraken/alerts",
        json={"pair": "XBTUSD", "condition": "sideways", "threshold": 70000},
    )
    invalid_drop = client.post(
        "/v1/market/kraken/alerts",
        json={"pair": "XBTUSD", "condition": "percent_down", "threshold": 100},
    )

    assert invalid_pair.status_code == 422
    assert invalid_condition.status_code == 422
    assert invalid_drop.status_code == 422


def test_price_alert_update_and_delete(monkeypatch):
    import app.price_alerts_api as api

    monkeypatch.setattr(
        api, "get_price_alert_repository", lambda: FakePriceAlertRepository()
    )
    paused = client.patch(
        "/v1/market/kraken/alerts/1", json={"is_active": False}
    )
    deleted = client.delete("/v1/market/kraken/alerts/1")

    assert paused.status_code == 200
    assert paused.json()["alert"]["status"] == "paused"
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True


def test_price_alert_missing_and_triggered_conflict(monkeypatch):
    import app.price_alerts_api as api

    monkeypatch.setattr(
        api, "get_price_alert_repository", lambda: FakePriceAlertRepository()
    )
    missing = client.patch(
        "/v1/market/kraken/alerts/404", json={"is_active": True}
    )
    conflict = client.patch(
        "/v1/market/kraken/alerts/5", json={"is_active": True}
    )

    assert missing.status_code == 404
    assert conflict.status_code == 409


def test_price_alert_requires_market_snapshot(monkeypatch):
    import app.price_alerts_api as api

    class NoSnapshotRepository(FakePriceAlertRepository):
        def create_alert(self, **kwargs):
            raise MarketDataNotReady

    monkeypatch.setattr(
        api, "get_price_alert_repository", lambda: NoSnapshotRepository()
    )
    response = client.post(
        "/v1/market/kraken/alerts",
        json={"pair": "XBTUSD", "condition": "below", "threshold": 60000},
    )

    assert response.status_code == 503
    assert "No stored market snapshot" in response.json()["detail"]


def test_price_alert_event_history(monkeypatch):
    import app.price_alerts_api as api

    monkeypatch.setattr(
        api, "get_price_alert_repository", lambda: FakePriceAlertRepository()
    )
    response = client.get("/v1/market/kraken/alerts/events?limit=10")

    assert response.status_code == 200
    assert response.json()["count"] == 1
