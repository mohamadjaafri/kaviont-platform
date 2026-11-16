import importlib

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


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


def test_kraken_ticker_endpoint_returns_market_data(monkeypatch) -> None:
    async def fake_fetch(pair: str) -> dict[str, object]:
        assert pair == "XBTUSD"
        return {
            "provider": "kraken",
            "pair": pair,
            "last_price": 65000.0,
            "bid": 64999.0,
            "ask": 65001.0,
            "volume_24h": 123.4,
            "high_24h": 66000.0,
            "low_24h": 64000.0,
            "retrieved_at": "2026-11-16T12:00:00+00:00",
        }

    monkeypatch.setattr("app.main.fetch_kraken_ticker", fake_fetch)
    response = client.get("/v1/market/kraken/ticker")

    assert response.status_code == 200
    assert response.json()["provider"] == "kraken"
    assert response.json()["pair"] == "XBTUSD"
    assert response.json()["last_price"] == 65000.0


def test_kraken_ticker_endpoint_normalizes_pair(monkeypatch) -> None:
    async def fake_fetch(pair: str) -> dict[str, object]:
        return {"provider": "kraken", "pair": pair}

    monkeypatch.setattr("app.main.fetch_kraken_ticker", fake_fetch)
    response = client.get("/v1/market/kraken/ticker?pair=xbteur")

    assert response.status_code == 200
    assert response.json()["pair"] == "XBTEUR"


def test_kraken_ticker_endpoint_rejects_invalid_pair() -> None:
    response = client.get("/v1/market/kraken/ticker?pair=BTC/USD")

    assert response.status_code == 422


def test_kraken_ticker_endpoint_maps_provider_failure(monkeypatch) -> None:
    from app.financial import FinancialDataProviderError

    async def fake_fetch(_pair: str) -> dict[str, object]:
        raise FinancialDataProviderError("internal provider detail")

    monkeypatch.setattr("app.main.fetch_kraken_ticker", fake_fetch)
    response = client.get("/v1/market/kraken/ticker")

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Market data provider is unavailable or returned invalid data"
    }
    assert "internal provider detail" not in response.text


def test_kraken_ticker_endpoint_maps_timeout(monkeypatch) -> None:
    from app.financial import FinancialDataTimeoutError

    async def fake_fetch(_pair: str) -> dict[str, object]:
        raise FinancialDataTimeoutError("internal timeout detail")

    monkeypatch.setattr("app.main.fetch_kraken_ticker", fake_fetch)
    response = client.get("/v1/market/kraken/ticker")

    assert response.status_code == 504
    assert response.json() == {"detail": "Market data provider timed out"}
    assert "internal timeout detail" not in response.text


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
