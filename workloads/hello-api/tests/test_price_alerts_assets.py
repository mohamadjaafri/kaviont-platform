from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_market_dashboard_loads_price_alert_assets():
    page = client.get("/market")

    assert page.status_code == 200
    assert "/market/assets/alerts.css" in page.text
    assert "/market/assets/alerts.js" in page.text
    assert 'id="alertForm"' in page.text

    script = client.get("/market/assets/alerts.js")
    stylesheet = client.get("/market/assets/alerts.css")

    assert script.status_code == 200
    assert 'request("/alerts"' in script.text
    assert stylesheet.status_code == 200
    assert ".alert-form" in stylesheet.text
