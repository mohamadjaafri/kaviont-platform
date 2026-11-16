import asyncio

import httpx
import pytest

from app.financial import (
    FinancialDataProviderError,
    FinancialDataTimeoutError,
    fetch_kraken_ticker,
)


def fetch_with_mock(handler):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_kraken_ticker("XBTUSD", client=client)

    return asyncio.run(run())


def test_kraken_ticker_parses_public_market_data() -> None:
    payload = {
        "error": [],
        "result": {
            "XXBTZUSD": {
                "a": ["65001.0", "1", "1.0"],
                "b": ["64999.0", "1", "1.0"],
                "c": ["65000.0", "0.01"],
                "v": ["1.0", "2.5"],
                "h": ["66000.0", "67000.0"],
                "l": ["64000.0", "63000.0"],
            }
        },
    }

    def handler(request):
        assert request.url.host == "api.kraken.com"
        assert request.url.path == "/0/public/Ticker"
        assert request.url.params["pair"] == "XBTUSD"
        return httpx.Response(200, json=payload)

    response = fetch_with_mock(handler)

    assert response["provider"] == "kraken"
    assert response["pair"] == "XBTUSD"
    assert response["last_price"] == 65000.0
    assert response["bid"] == 64999.0
    assert response["ask"] == 65001.0
    assert response["volume_24h"] == 2.5
    assert response["high_24h"] == 67000.0
    assert response["low_24h"] == 63000.0
    assert response["retrieved_at"]


def test_kraken_provider_errors_are_normalized() -> None:
    def handler(_request):
        return httpx.Response(
            200,
            json={"error": ["EQuery:Unknown asset pair"], "result": {}},
        )

    with pytest.raises(FinancialDataProviderError):
        fetch_with_mock(handler)


def test_kraken_invalid_payload_is_normalized() -> None:
    def handler(_request):
        return httpx.Response(200, json={"error": [], "result": {}})

    with pytest.raises(FinancialDataProviderError):
        fetch_with_mock(handler)


def test_kraken_http_failure_is_normalized() -> None:
    def handler(_request):
        return httpx.Response(503, json={"error": ["Service unavailable"]})

    with pytest.raises(FinancialDataProviderError):
        fetch_with_mock(handler)


def test_kraken_timeout_is_normalized() -> None:
    def handler(request):
        raise httpx.ReadTimeout("provider timeout", request=request)

    with pytest.raises(FinancialDataTimeoutError):
        fetch_with_mock(handler)
