import os
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query

from app.financial import (
    FinancialDataProviderError,
    FinancialDataTimeoutError,
    fetch_kraken_ticker,
)
from app.observability import configure_observability
from app.secrets import secret_is_configured

environment = os.getenv("KAVIONT_ENV", "production").strip().lower()
enable_api_docs = environment in {"local", "test"}

app = FastAPI(
    title="Kaviont Hello API",
    version="0.7.0",
    docs_url="/docs" if enable_api_docs else None,
    redoc_url="/redoc" if enable_api_docs else None,
    openapi_url="/openapi.json" if enable_api_docs else None,
)

configure_observability(app)


@app.get("/", tags=["service"])
def root() -> dict[str, str]:
    return {"service": "hello-api", "status": "running", "version": "0.7.0"}


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
async def kraken_ticker(
    pair: Annotated[
        str,
        Query(
            min_length=5,
            max_length=12,
            pattern=r"^[A-Za-z0-9]+$",
            description="Kraken REST market pair, for example XBTUSD or XBTEUR.",
        ),
    ] = "XBTUSD",
) -> dict[str, object]:
    """Return a normalized ticker snapshot from Kraken's public market-data API."""
    try:
        return await fetch_kraken_ticker(pair.upper())
    except FinancialDataTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="Market data provider timed out",
        ) from exc
    except FinancialDataProviderError as exc:
        raise HTTPException(
            status_code=502,
            detail="Market data provider is unavailable or returned invalid data",
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
