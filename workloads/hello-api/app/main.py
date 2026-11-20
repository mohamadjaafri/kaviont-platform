import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.market_repository import (
    MarketDataNotReady,
    MarketDataRepository,
    MarketDataStorageNotConfigured,
)
from app.observability import configure_observability
from app.engineering_api import router as engineering_router
from app.secrets import secret_is_configured

environment = os.getenv("KAVIONT_ENV", "production").strip().lower()
enable_api_docs = environment in {"local", "test"}
market_pair = os.getenv("KRAKEN_MARKET_PAIR", "XBTUSD").strip().upper()
market_poll_interval = int(os.getenv("KRAKEN_POLL_INTERVAL_SECONDS", "60"))
PAIR_PATTERN = r"^[A-Za-z0-9]{5,12}$"
MarketRange = Literal["1h", "24h", "7d"]

app = FastAPI(
    title="Kaviont Hello API",
    version="0.9.0",
    docs_url="/docs" if enable_api_docs else None,
    redoc_url="/redoc" if enable_api_docs else None,
    openapi_url="/openapi.json" if enable_api_docs else None,
)

MARKET_DASHBOARD_DIR = Path(__file__).resolve().parent / "static" / "market"
ENGINEERING_PORTAL_DIR = Path(__file__).resolve().parent / "static" / "engineering"
app.mount(
    "/engineering/assets",
    StaticFiles(directory=ENGINEERING_PORTAL_DIR / "assets"),
    name="engineering-portal-assets",
)
app.mount(
    "/market/assets",
    StaticFiles(directory=MARKET_DASHBOARD_DIR / "assets"),
    name="market-dashboard-assets",
)

configure_observability(app)
app.include_router(engineering_router)


@app.middleware("http")
async def prevent_engineering_data_caching(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/v1/engineering/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/market", include_in_schema=False)
def market_dashboard() -> FileResponse:
    """Serve the interactive Kaviont Live market dashboard."""
    return FileResponse(
        MARKET_DASHBOARD_DIR / "index.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/engineering/", include_in_schema=False)
@app.get("/engineering", include_in_schema=False)
def engineering_portal() -> FileResponse:
    """Serve the Kaviont Engineering Portal."""
    return FileResponse(
        ENGINEERING_PORTAL_DIR / "index.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/engineering/manifest.webmanifest", include_in_schema=False)
def engineering_manifest() -> FileResponse:
    """Serve the installable app manifest."""
    return FileResponse(
        ENGINEERING_PORTAL_DIR / "manifest.webmanifest",
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/engineering/service-worker.js", include_in_schema=False)
def engineering_service_worker() -> FileResponse:
    """Serve the PWA worker with a deliberately narrow scope."""
    return FileResponse(
        ENGINEERING_PORTAL_DIR / "service-worker.js",
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache",
            "Service-Worker-Allowed": "/engineering/",
        },
    )


def get_market_repository() -> MarketDataRepository:
    """Create a repository from runtime configuration without connecting at import."""
    return MarketDataRepository.from_environment()


def _storage_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MarketDataStorageNotConfigured):
        return HTTPException(
            status_code=503,
            detail="Market data storage is not configured",
        )
    return HTTPException(
        status_code=503,
        detail="Market data storage is unavailable",
    )


@app.get("/", tags=["service"])
def root() -> dict[str, str]:
    return {"service": "hello-api", "status": "running", "version": "0.9.0"}


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
    except Exception as exc:
        raise _storage_error(exc) from exc


@app.get("/v1/market/kraken/tickers", tags=["market-data"])
def kraken_tickers() -> dict[str, object]:
    """Return the newest stored snapshot for each tracked Kraken market pair."""
    try:
        return get_market_repository().latest_tickers(market_poll_interval)
    except Exception as exc:
        raise _storage_error(exc) from exc


@app.get("/v1/market/kraken/history", tags=["market-data"])
def kraken_history(
    pair: str = Query(
        default=market_pair,
        min_length=5,
        max_length=12,
        pattern=PAIR_PATTERN,
    ),
    time_range: MarketRange = Query(default="24h", alias="range"),
    limit: int = Query(default=500, ge=2, le=2000),
) -> dict[str, object]:
    """Return a downsampled chronological ticker series for a requested range."""
    try:
        return get_market_repository().historical_ticker(
            pair.strip().upper(),
            time_range,
            limit,
        )
    except Exception as exc:
        raise _storage_error(exc) from exc


@app.get("/v1/market/kraken/summary", tags=["market-data"])
def kraken_summary(
    pair: str = Query(
        default=market_pair,
        min_length=5,
        max_length=12,
        pattern=PAIR_PATTERN,
    ),
    time_range: MarketRange = Query(default="24h", alias="range"),
) -> dict[str, object]:
    """Return price change, high/low, average, and sample count for a range."""
    try:
        return get_market_repository().market_summary(
            pair.strip().upper(),
            time_range,
        )
    except Exception as exc:
        raise _storage_error(exc) from exc


@app.get("/v1/market/kraken/status", tags=["market-data"])
def kraken_worker_status() -> dict[str, object]:
    """Report the dedicated worker state and latest heartbeat."""
    try:
        return get_market_repository().worker_status(
            market_pair,
            market_poll_interval,
        )
    except Exception as exc:
        raise _storage_error(exc) from exc


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
