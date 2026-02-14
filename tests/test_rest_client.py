import httpx
import pytest

from binance_minute_lake.sources.rest import BinanceRESTClient


def test_rest_client_retries_on_429_then_succeeds() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(
                status_code=429,
                request=request,
                headers={"Retry-After": "0"},
                json={"code": -1003, "msg": "Too many requests"},
            )
        return httpx.Response(
            status_code=200,
            request=request,
            json={
                "markPrice": "100.0",
                "indexPrice": "99.0",
                "lastFundingRate": "0.0001",
                "nextFundingTime": 0,
                "predictedFundingRate": "0.0002",
                "time": 123,
            },
        )

    client = BinanceRESTClient(
        base_url="https://fapi.binance.com",
        retries=3,
        transport=httpx.MockTransport(handler),
    )
    try:
        payload = client.fetch_premium_index("BTCUSDT")
    finally:
        client.close()

    assert call_count == 3
    assert payload["mark_price"] == 100.0
    assert payload["index_price"] == 99.0
    assert payload["predicted_funding"] == 0.0002


def test_rest_client_does_not_retry_on_400() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(status_code=400, request=request, json={"code": -1100, "msg": "Bad request"})

    client = BinanceRESTClient(
        base_url="https://fapi.binance.com",
        retries=5,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(httpx.HTTPStatusError):
            client.fetch_open_interest("BTCUSDT")
    finally:
        client.close()

    assert call_count == 1
