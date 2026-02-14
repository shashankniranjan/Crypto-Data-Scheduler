from datetime import date

from binance_minute_lake.sources.vision import VisionClient


def test_vision_klines_url_pattern() -> None:
    client = VisionClient(base_url="https://data.binance.vision/data/futures/um/daily")
    try:
        value = client.build_daily_zip_url(
            stream="klines",
            symbol="BTCUSDT",
            trade_date=date(2026, 1, 15),
            interval="1m",
        )
    finally:
        client.close()

    assert (
        value
        == "https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2026-01-15.zip"
    )


def test_vision_metrics_url_pattern() -> None:
    client = VisionClient(base_url="https://data.binance.vision/data/futures/um/daily")
    try:
        value = client.build_daily_zip_url(
            stream="metrics",
            symbol="BTCUSDT",
            trade_date=date(2026, 1, 15),
        )
    finally:
        client.close()

    assert (
        value
        == "https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2026-01-15.zip"
    )
