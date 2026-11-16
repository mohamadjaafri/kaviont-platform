import os

from fastapi import FastAPI, HTTPException

from app.market_repository import (
    MarketDataNotReady,
    MarketDataRepository,
    MarketDataStorageNotConfigured,
)
from app.observability import configure_observability
from app.secrets import secret_is_configured

environment = os.getenv("KAVIONT_ENV", "production").strip().lower()
enable_api_docs = environment in {"local", "test"}
market_pair = os.getenv("KRAKEN_MARKET_PAIR", "XBTUSD").strip().upper()
market_poll_interval = int(os.getenv("KRAKEN_POLL_INTERVAL_SECONDS", "60"))

app = FastAPI(
    title="Kaviont Hello API",
    version="0.8.0",
    docs_url="/docs" if enable_api_docs else None,
    redoc_url="/redoc" if enable_api_docs else None,
    openapi_url="/openapi.json" if enable_api_docs else None,
)

configure_observability(app)


def get_market_repository() -> MarketDataRepository:
    """Create a repository from runtime configuration without connecting at import."""
    return MarketDataRepository.from_environment()


@app.get("/", tags=["service"])
def root() -> dict[str, str]:
    return {"service": "hello-api", "status": "running", "version": "0.8.0"}


@app.get("/healthz", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", tags=["health"])
def readiness() -> dict[str, str]:
    return {"status": "ready"}


if enable_api_docs:

    @app.get("/__test__/error", tags=["testing"])
    def inject_test_error() -> None:
        """Generate a controlled 500 response for local alert demonstrations."""
        raise HTTPException(
            status_code=500,
            detail="Intentional local test failure",
        )


@app.get("/v1/market/kraken/ticker", tags=["market-data"])
def kraken_ticker() -> dict[str, object]:
    """Return the latest persisted Kraken ticker snapshot."""
    try:
        return get_market_repository().latest_snapshot(
            market_pair,
            market_poll_interval,
        )
    except MarketDataNotReady as exc:
        raise HTTPException(
            status_code=503,
            detail="Market data is not available yet; the worker has not stored a snapshot",
        ) from exc
    except MarketDataStorageNotConfigured as exc:
        raise HTTPException(
            status_code=503,
            detail="Market data storage is not configured",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Market data storage is unavailable",
        ) from exc


@app.get("/v1/market/kraken/status", tags=["market-data"])
def kraken_worker_status() -> dict[str, object]:
    """Report the dedicated worker state and latest heartbeat."""
    try:
        return get_market_repository().worker_status(
            market_pair,
            market_poll_interval,
        )
    except MarketDataStorageNotConfigured as exc:
        raise HTTPException(
            status_code=503,
            detail="Market data storage is not configured",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Market data storage is unavailable",
        ) from exc


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
