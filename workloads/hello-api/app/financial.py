"""Public financial market data integration with explicit telemetry."""

from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from time import perf_counter
from typing import Any

import httpx
from opentelemetry import metrics, trace
from opentelemetry.trace import SpanKind, Status, StatusCode

KRAKEN_TICKER_URL = "https://api.kraken.com/0/public/Ticker"
REQUEST_TIMEOUT = httpx.Timeout(5.0, connect=2.0)

_meter = metrics.get_meter("kaviont.financial-data")
_tracer = trace.get_tracer("kaviont.financial-data")

_request_counter = _meter.create_counter(
    "financial.api.requests",
    unit="{request}",
    description="Number of requests made to external financial-data providers.",
)
_request_duration = _meter.create_histogram(
    "financial.api.request.duration",
    unit="s",
    description="Duration of external financial-data provider requests.",
)


class FinancialDataProviderError(Exception):
    """Raised when the external provider fails or returns an invalid payload."""


class FinancialDataTimeoutError(FinancialDataProviderError):
    """Raised when the external provider does not respond before the timeout."""


def _number(
    ticker: dict[str, Any],
    field: str,
    index: int,
    *,
    allow_zero: bool = False,
) -> float:
    values = ticker.get(field)
    if not isinstance(values, (list, tuple)) or len(values) <= index:
        raise ValueError(f"Missing ticker field: {field}")

    value = float(values[index])
    if not isfinite(value) or (value < 0 if allow_zero else value <= 0):
        raise ValueError(f"Invalid ticker field: {field}")
    return value


def _normalize_ticker(payload: Any, pair: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("Kraken response must be a JSON object")

    provider_errors = payload.get("error")
    if provider_errors:
        raise FinancialDataProviderError("Kraken rejected the market-data request")

    result = payload.get("result")
    if not isinstance(result, dict) or not result:
        raise ValueError("Kraken response does not contain ticker data")

    ticker = next(iter(result.values()))
    if not isinstance(ticker, dict):
        raise ValueError("Kraken ticker data has an unexpected shape")

    return {
        "provider": "kraken",
        "pair": pair,
        "last_price": _number(ticker, "c", 0),
        "bid": _number(ticker, "b", 0),
        "ask": _number(ticker, "a", 0),
        "volume_24h": _number(ticker, "v", 1, allow_zero=True),
        "high_24h": _number(ticker, "h", 1),
        "low_24h": _number(ticker, "l", 1),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


async def fetch_kraken_ticker(
    pair: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, object]:
    """Fetch one ticker snapshot. An injected client keeps tests fully offline."""
    started_at = perf_counter()
    outcome = "error"
    metric_attributes = {"provider": "kraken", "pair": pair}

    with _tracer.start_as_current_span(
        "kraken.public_ticker",
        kind=SpanKind.CLIENT,
    ) as span:
        span.set_attribute("server.address", "api.kraken.com")
        span.set_attribute("server.port", 443)
        span.set_attribute("http.request.method", "GET")
        span.set_attribute("url.path", "/0/public/Ticker")
        span.set_attribute("kaviont.market.pair", pair)

        try:
            if client is None:
                async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as owned_client:
                    response = await owned_client.get(
                        KRAKEN_TICKER_URL,
                        params={"pair": pair},
                    )
            else:
                response = await client.get(
                    KRAKEN_TICKER_URL,
                    params={"pair": pair},
                )

            span.set_attribute("http.response.status_code", response.status_code)
            response.raise_for_status()
            ticker = _normalize_ticker(response.json(), pair)

            outcome = "success"
            span.set_status(Status(StatusCode.OK))
            return ticker

        except FinancialDataProviderError as exc:
            outcome = "provider_error"
            span.set_attribute("error.type", "provider_error")
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, "Kraken returned an error"))
            raise

        except httpx.TimeoutException as exc:
            outcome = "timeout"
            span.set_attribute("error.type", "timeout")
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, "Kraken request timed out"))
            raise FinancialDataTimeoutError("Kraken API request timed out") from exc

        except httpx.HTTPError as exc:
            outcome = "http_error"
            if isinstance(exc, httpx.HTTPStatusError):
                span.set_attribute("http.response.status_code", exc.response.status_code)
            span.set_attribute("error.type", "http_error")
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, "Kraken HTTP request failed"))
            raise FinancialDataProviderError("Kraken API request failed") from exc

        except (ValueError, TypeError, KeyError, StopIteration) as exc:
            outcome = "invalid_response"
            span.set_attribute("error.type", "invalid_response")
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, "Kraken returned invalid data"))
            raise FinancialDataProviderError(
                "Kraken returned an invalid market-data payload"
            ) from exc

        finally:
            _request_counter.add(1, {**metric_attributes, "outcome": outcome})
            _request_duration.record(
                perf_counter() - started_at,
                metric_attributes,
            )
