import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request

from app.market_poller import KrakenTickerPoller, MarketDataNotReady
from app.observability import configure_observability
from app.secrets import secret_is_configured

environment = os.getenv("KAVIONT_ENV", "production").strip().lower()
enable_api_docs = environment in {"local", "test"}

kraken_poller = KrakenTickerPoller.from_environment()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Start automatic market-data polling and stop it during shutdown."""
    await kraken_poller.start()
    try:
        yield
    finally:
        await kraken_poller.stop()


app = FastAPI(
    title="Kaviont Hello API",
    version="0.7.0",
    docs_url="/docs" if enable_api_docs else None,
    redoc_url="/redoc" if enable_api_docs else None,
    openapi_url="/openapi.json" if enable_api_docs else None,
    lifespan=lifespan,
)

configure_observability(app)


def get_poller(request: Request) -> KrakenTickerPoller:
    return getattr(request.app.state, "kraken_poller", kraken_poller)


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
def kraken_ticker(request: Request) -> dict[str, object]:
    """Return the latest automatically refreshed Kraken ticker snapshot."""
    try:
        return get_poller(request).get_snapshot()
    except MarketDataNotReady as exc:
        raise HTTPException(
            status_code=503,
            detail="Market data is not available yet; the background poller is starting",
        ) from exc


@app.get("/v1/market/kraken/status", tags=["market-data"])
def kraken_poller_status(request: Request) -> dict[str, object]:
    """Report background polling and cached market-data freshness."""
    return get_poller(request).status()


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
