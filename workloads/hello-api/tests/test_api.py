from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_returns_service_metadata() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "service": "hello-api",
        "status": "running",
        "version": "0.2.0",
    }


def test_health_endpoint() -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_endpoint() -> None:
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_api_docs_are_enabled_in_local_environment(monkeypatch) -> None:
    monkeypatch.setenv("KAVIONT_ENV", "local")
    from app.main import FastAPI

    local_app = FastAPI(
        title="Kaviont Hello API",
        version="0.2.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    local_client = TestClient(local_app)

    assert local_client.get("/docs").status_code == 200
    assert local_client.get("/redoc").status_code == 200
    assert local_client.get("/openapi.json").status_code == 200


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
