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
    assert 'id="kubeEventTable"' in page.text
    assert 'id="view-templates"' in page.text

    script = client.get("/engineering/assets/engineering.js")
    stylesheet = client.get("/engineering/assets/engineering.css")

    assert script.status_code == 200
    assert 'request("/repositories"' in script.text
    assert 'request("/cloud"' in script.text
    assert 'data-template-download' in script.text
    assert 'request("/cloud")' in script.text
    assert '#kubeEventTable' in script.text
    assert stylesheet.status_code == 200
    assert ".portal-shell" in stylesheet.text


def test_engineering_portal_exposes_installable_pwa_manifest_and_worker():
    manifest = client.get("/engineering/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    assert manifest.json()["start_url"] == "/engineering/"
    assert manifest.json()["display"] == "standalone"

    worker = client.get("/engineering/service-worker.js")
    assert worker.status_code == 200
    assert worker.headers["service-worker-allowed"] == "/engineering/"
    assert 'url.pathname.startsWith("/v1/")' in worker.text

    icon = client.get("/engineering/assets/kaviont-icon.svg")
    assert icon.status_code == 200
    assert "<svg" in icon.text
