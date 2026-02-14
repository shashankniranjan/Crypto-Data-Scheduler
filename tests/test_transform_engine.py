from datetime import UTC, datetime

from binance_minute_lake.transforms.minute_builder import MinuteTransformEngine


def test_transform_engine_returns_canonical_columns() -> None:
    engine = MinuteTransformEngine(max_ffill_minutes=60)
    start = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)
    end = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)

    frame = engine.build_canonical_frame(
        start_minute=start,
        end_minute=end,
        klines=[
            {
                "open_time": int(start.timestamp() * 1000),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume_btc": 2.0,
                "volume_usdt": 200000.0,
                "trade_count": 20,
                "taker_buy_vol_btc": 1.1,
                "taker_buy_vol_usdt": 110000.0,
            }
        ],
        mark_price_klines=[
            {
                "open_time": int(start.timestamp() * 1000),
                "mark_price_open": 100.1,
                "mark_price_high": 101.2,
                "mark_price_low": 99.1,
                "mark_price_close": 100.4,
            }
        ],
        index_price_klines=[
            {
                "open_time": int(start.timestamp() * 1000),
                "index_price_open": 100.0,
                "index_price_high": 101.1,
                "index_price_low": 99.0,
                "index_price_close": 100.2,
            }
        ],
        agg_trades=[],
        funding_rates=[],
    )

    assert frame.height == 1
    assert frame.width == 58
    row = frame.row(0, named=True)
    assert row["vwap_1m"] == row["close"]
    assert row["open"] == 100.0
