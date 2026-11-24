"""HTTP routes for managing persistent market price alerts."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.market_repository import MarketDataNotReady, MarketDataStorageNotConfigured
from app.price_alerts import (
    PriceAlertConflict,
    PriceAlertNotFound,
    PriceAlertRepository,
)

router = APIRouter(prefix="/v1/market/kraken", tags=["market-alerts"])


class PriceAlertCreateRequest(BaseModel):
    pair: str = Field(min_length=5, max_length=12, pattern=r"^[A-Za-z0-9]{5,12}$")
    condition: Literal["above", "below", "percent_up", "percent_down"]
    threshold: float = Field(gt=0, le=1000000000000)


class PriceAlertUpdateRequest(BaseModel):
    is_active: bool


def get_price_alert_repository() -> PriceAlertRepository:
    return PriceAlertRepository.from_environment()


def _raise_storage_error(exc: Exception) -> None:
    if isinstance(exc, MarketDataStorageNotConfigured):
        raise HTTPException(
            status_code=503,
            detail="Market data storage is not configured",
        ) from exc
    raise HTTPException(
        status_code=503,
        detail="Market alert storage is unavailable",
    ) from exc


@router.get("/alerts")
def list_price_alerts() -> dict[str, object]:
    try:
        alerts = get_price_alert_repository().list_alerts()
        return {"count": len(alerts), "alerts": alerts}
    except Exception as exc:
        _raise_storage_error(exc)


@router.post("/alerts", status_code=201)
def create_price_alert(request: PriceAlertCreateRequest) -> dict[str, object]:
    if request.condition in {"percent_up", "percent_down"} and request.threshold > 10000:
        raise HTTPException(
            status_code=422,
            detail="percentage threshold must not exceed 10000",
        )
    if request.condition == "percent_down" and request.threshold >= 100:
        raise HTTPException(
            status_code=422,
            detail="percent_down threshold must be below 100",
        )
    try:
        alert = get_price_alert_repository().create_alert(
            pair=request.pair,
            condition=request.condition,
            threshold=request.threshold,
        )
        return {"alert": alert}
    except MarketDataNotReady as exc:
        raise HTTPException(
            status_code=503,
            detail="No stored market snapshot exists for this pair yet",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        _raise_storage_error(exc)


@router.get("/alerts/events")
def list_price_alert_events(
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, object]:
    try:
        events = get_price_alert_repository().list_events(limit)
        return {"count": len(events), "events": events}
    except Exception as exc:
        _raise_storage_error(exc)


@router.patch("/alerts/{alert_id}")
def update_price_alert(
    alert_id: int,
    request: PriceAlertUpdateRequest,
) -> dict[str, object]:
    try:
        alert = get_price_alert_repository().set_alert_active(
            alert_id, request.is_active
        )
        return {"alert": alert}
    except PriceAlertNotFound as exc:
        raise HTTPException(status_code=404, detail="Price alert not found") from exc
    except PriceAlertConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        _raise_storage_error(exc)


@router.delete("/alerts/{alert_id}")
def delete_price_alert(alert_id: int) -> dict[str, object]:
    try:
        get_price_alert_repository().delete_alert(alert_id)
        return {"deleted": True, "id": alert_id}
    except PriceAlertNotFound as exc:
        raise HTTPException(status_code=404, detail="Price alert not found") from exc
    except Exception as exc:
        _raise_storage_error(exc)
