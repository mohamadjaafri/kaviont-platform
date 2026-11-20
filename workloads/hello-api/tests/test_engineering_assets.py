from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_engineering_portal_serves_html_and_assets():
    page = client.get("/engineering")

    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "<title>Kaviont Engineering Platform</title>" in page.text
    assert 'id="view-repositories"' in page.text
    assert 'id="view-security"' in page.text
    assert 'id="view-runtime"' in page.text
    assert 'id="view-templates"' in page.text

    script = client.get("/engineering/assets/engineering.js")
    stylesheet = client.get("/engineering/assets/engineering.css")

    assert script.status_code == 200
    assert 'request("/repositories"' in script.text
    assert 'request("/cloud"' in script.text
    assert 'data-template-download' in script.text
    assert stylesheet.status_code == 200
    assert ".portal-shell" in stylesheet.text
