import importlib

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class ReadyPoller:
    def get_snapshot(self):
        return {
            "provider": "kraken",
            "pair": "XBTUSD",
            "last_price": 65000.0,
            "bid": 64999.0,
            "ask": 65001.0,
            "volume_24h": 123.4,
            "high_24h": 66000.0,
            "low_24h": 64000.0,
            "retrieved_at": "2026-11-16T12:00:00+00:00",
            "cache_age_seconds": 2.0,
            "stale": False,
            "poll_interval_seconds": 60.0,
        }

    def status(self):
        return {
            "provider": "kraken",
            "pair": "XBTUSD",
            "polling_enabled": True,
            "poll_interval_seconds": 60.0,
            "has_snapshot": True,
            "cache_age_seconds": 2.0,
            "stale": False,
            "last_attempt_at": "2026-11-16T12:00:00+00:00",
            "last_successful_update": "2026-11-16T12:00:00+00:00",
            "last_error": None,
            "running": True,
        }


class EmptyPoller:
    def get_snapshot(self):
        from app.market_poller import MarketDataNotReady

        raise MarketDataNotReady

    def status(self):
        return {"polling_enabled": True, "has_snapshot": False, "running": True}


def test_root_returns_service_metadata() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "service": "hello-api",
        "status": "running",
        "version": "0.7.0",
    }


def test_health_endpoint() -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_endpoint() -> None:
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_kraken_ticker_endpoint_returns_cached_snapshot(monkeypatch) -> None:
    import app.main as main_module

    monkeypatch.setattr(main_module, "kraken_poller", ReadyPoller())
    response = client.get("/v1/market/kraken/ticker")

    assert response.status_code == 200
    assert response.json()["provider"] == "kraken"
    assert response.json()["pair"] == "XBTUSD"
    assert response.json()["last_price"] == 65000.0
    assert response.json()["cache_age_seconds"] == 2.0


def test_kraken_ticker_endpoint_returns_503_before_first_success(monkeypatch) -> None:
    import app.main as main_module

    monkeypatch.setattr(main_module, "kraken_poller", EmptyPoller())
    response = client.get("/v1/market/kraken/ticker")

    assert response.status_code == 503
    assert "background poller is starting" in response.json()["detail"]


def test_kraken_poller_status_endpoint(monkeypatch) -> None:
    import app.main as main_module

    monkeypatch.setattr(main_module, "kraken_poller", ReadyPoller())
    response = client.get("/v1/market/kraken/status")

    assert response.status_code == 200
    assert response.json()["polling_enabled"] is True
    assert response.json()["pair"] == "XBTUSD"


def test_api_docs_are_enabled_in_local_environment(monkeypatch) -> None:
    monkeypatch.setenv("KAVIONT_ENV", "local")
    import app.main as main_module

    main_module = importlib.reload(main_module)
    local_client = TestClient(main_module.app)

    assert local_client.get("/docs").status_code == 200
    assert local_client.get("/redoc").status_code == 200
    assert local_client.get("/openapi.json").status_code == 200


def test_api_docs_are_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("KAVIONT_ENV", raising=False)
    import app.main as main_module

    main_module = importlib.reload(main_module)
    production_client = TestClient(main_module.app)

    assert production_client.get("/docs").status_code == 404
    assert production_client.get("/redoc").status_code == 404
    assert production_client.get("/openapi.json").status_code == 404


def test_local_error_injection_is_available_only_outside_production(monkeypatch) -> None:
    monkeypatch.setenv("KAVIONT_ENV", "local")
    import app.main as main_module

    main_module = importlib.reload(main_module)
    local_client = TestClient(main_module.app)
    response = local_client.get("/__test__/error")

    assert response.status_code == 500
    assert response.json() == {"detail": "Intentional local test failure"}

    monkeypatch.delenv("KAVIONT_ENV", raising=False)
    main_module = importlib.reload(main_module)
    production_client = TestClient(main_module.app)

    assert production_client.get("/__test__/error").status_code == 404


def test_secret_status_uses_local_mode_without_vault(monkeypatch) -> None:
    monkeypatch.delenv("KEY_VAULT_URL", raising=False)
    monkeypatch.delenv("LOCAL_DEMO_SECRET", raising=False)

    response = client.get("/v1/secret-status")

    assert response.status_code == 200
    assert response.json() == {"mode": "local", "secret_configured": False}


def test_local_secret_status_reports_presence_without_returning_value(monkeypatch) -> None:
    monkeypatch.delenv("KEY_VAULT_URL", raising=False)
    monkeypatch.setenv("LOCAL_DEMO_SECRET", "local-only-test-value")

    response = client.get("/v1/secret-status")

    assert response.status_code == 200
    assert response.json() == {"mode": "local", "secret_configured": True}
    assert "local-only-test-value" not in response.text


def test_secret_status_never_returns_secret_value(monkeypatch) -> None:
    monkeypatch.setenv("KEY_VAULT_URL", "https://example.vault.azure.net/")
    monkeypatch.setenv("KEY_VAULT_SECRET_NAME", "platform-demo-token")
    monkeypatch.setattr("app.main.secret_is_configured", lambda _url, _name: True)

    response = client.get("/v1/secret-status")

    assert response.status_code == 200
    assert response.json() == {"mode": "azure-key-vault", "secret_configured": True}
    assert "value" not in response.json()


def test_secret_status_returns_safe_error_when_vault_is_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("KEY_VAULT_URL", "https://example.vault.azure.net/")
    monkeypatch.setattr(
        "app.main.secret_is_configured",
        lambda _url, _name: (_ for _ in ()).throw(RuntimeError("sensitive diagnostic")),
    )

    response = client.get("/v1/secret-status")

    assert response.status_code == 503
    assert response.json() == {"detail": "Secret store is unavailable"}
    assert "sensitive diagnostic" not in response.text
