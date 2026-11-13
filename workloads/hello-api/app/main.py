import os

from fastapi import FastAPI, HTTPException

from app.observability import configure_observability
from app.secrets import secret_is_configured

environment = os.getenv("KAVIONT_ENV", "production").strip().lower()
enable_api_docs = environment in {"local", "test"}

app = FastAPI(
    title="Kaviont Hello API",
    version="0.5.0",
    docs_url="/docs" if enable_api_docs else None,
    redoc_url="/redoc" if enable_api_docs else None,
    openapi_url="/openapi.json" if enable_api_docs else None,
)

configure_observability(app)


@app.get("/", tags=["service"])
def root() -> dict[str, str]:
    return {"service": "hello-api", "status": "running", "version": "0.5.0"}


@app.get("/healthz", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", tags=["health"])
def readiness() -> dict[str, str]:
    return {"status": "ready"}


@app.get("/v1/secret-status", tags=["configuration"])
def secret_status() -> dict[str, bool | str]:
    """Report secret presence without exposing the secret or its metadata."""
    vault_url = os.getenv("KEY_VAULT_URL", "").strip()
    secret_name = os.getenv("KEY_VAULT_SECRET_NAME", "platform-demo-token").strip()

    if not vault_url:
        local_secret = os.getenv("LOCAL_DEMO_SECRET", "")
        return {"mode": "local", "secret_configured": bool(local_secret.strip())}

    try:
        configured = secret_is_configured(vault_url, secret_name)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Secret store is unavailable",
        ) from exc

    return {"mode": "azure-key-vault", "secret_configured": configured}
