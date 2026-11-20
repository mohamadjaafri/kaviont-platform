import struct

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_engineering_portal_exposes_pwa_metadata_and_mobile_shell():
    response = client.get("/engineering/")

    assert response.status_code == 200
    assert '<link rel="manifest" href="/engineering/manifest.webmanifest">' in response.text
    assert 'apple-mobile-web-app-capable' in response.text
    assert 'id="pwaInstall"' in response.text
    assert 'class="mobile-dock"' in response.text
    assert 'id="mobileMoreMenu"' in response.text
    assert 'id="installHelp"' in response.text


def test_pwa_manifest_has_installable_mobile_configuration():
    response = client.get("/engineering/manifest.webmanifest")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/manifest+json")
    manifest = response.json()
    assert manifest["name"] == "Kaviont Engineering Platform"
    assert manifest["start_url"] == "/engineering/?source=installed-app"
    assert manifest["scope"] == "/engineering/"
    assert manifest["display"] == "standalone"
    icon_sizes = {item["sizes"] for item in manifest["icons"]}
    assert {"192x192", "512x512"} <= icon_sizes


def test_pwa_service_worker_is_scoped_to_engineering_path():
    response = client.get("/engineering/service-worker.js")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/javascript")
    assert response.headers["service-worker-allowed"] == "/engineering/"
    assert 'url.pathname.startsWith("/v1/")' in response.text
    assert 'event.respondWith(fetch(request))' in response.text
    assert "caches.match(request)" in response.text


def test_pwa_icons_are_valid_pngs_with_expected_dimensions():
    for path, expected_size in (
        ("/engineering/assets/icon-180.png", 180),
        ("/engineering/assets/icon-192.png", 192),
        ("/engineering/assets/icon-512.png", 512),
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert response.content[:8] == b"\x89PNG\r\n\x1a\n"
        width, height = struct.unpack(">II", response.content[16:24])
        assert (width, height) == (expected_size, expected_size)


def test_mobile_pwa_assets_register_service_worker_and_install_prompt():
    response = client.get("/engineering/assets/engineering.js")

    assert response.status_code == 200
    assert 'navigator.serviceWorker.register("/engineering/service-worker.js"' in response.text
    assert 'beforeinstallprompt' in response.text
    assert 'Add to Home Screen' in response.text
    assert 'display-mode: standalone' in response.text
