from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from binance_minute_lake.validation.partition_audit import audit_hour_partition_file


def _build_partition_frame(start: datetime, end: datetime) -> pl.DataFrame:
    timestamps = pl.datetime_range(
        start=start,
        end=end,
        interval="1m",
        eager=True,
        time_zone="UTC",
    )
    row_count = timestamps.len()
    return pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": [1.0] * row_count,
            "high": [1.0] * row_count,
            "low": [1.0] * row_count,
            "close": [1.0] * row_count,
            "volume_btc": [1.0] * row_count,
            "volume_usdt": [1.0] * row_count,
            "trade_count": [1] * row_count,
            "mark_price_open": [1.0] * row_count,
            "mark_price_close": [1.0] * row_count,
            "index_price_open": [1.0] * row_count,
            "index_price_close": [1.0] * row_count,
        }
    )


def test_partition_audit_detects_missing_file(tmp_path: Path) -> None:
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    end = start + timedelta(minutes=59)
    result = audit_hour_partition_file(tmp_path / "missing.parquet", start, end)
    assert not result.is_valid
    assert result.reason == "missing_file"


def test_partition_audit_validates_full_hour_partition(tmp_path: Path) -> None:
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    end = start + timedelta(minutes=59)
    path = tmp_path / "part.parquet"
    _build_partition_frame(start, end).write_parquet(path)

    result = audit_hour_partition_file(path, start, end)
    assert result.is_valid
    assert result.reason == "ok"


def test_partition_audit_detects_gap(tmp_path: Path) -> None:
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    end = start + timedelta(minutes=59)
    path = tmp_path / "part.parquet"

    frame = _build_partition_frame(start, end).filter(pl.col("timestamp") != start + timedelta(minutes=17))
    frame.write_parquet(path)

    result = audit_hour_partition_file(path, start, end)
    assert not result.is_valid
    assert result.reason.startswith("row_count_mismatch")


def test_partition_audit_detects_missing_hard_required_column(tmp_path: Path) -> None:
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    end = start + timedelta(minutes=59)
    path = tmp_path / "part.parquet"

    frame = _build_partition_frame(start, end).drop("index_price_close")
    frame.write_parquet(path)

    result = audit_hour_partition_file(path, start, end)
    assert not result.is_valid
    assert result.reason.startswith("missing_columns:")


def test_partition_audit_accepts_full_hour_for_partial_window(tmp_path: Path) -> None:
    hour_start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    hour_end = hour_start + timedelta(minutes=59)
    path = tmp_path / "part.parquet"
    _build_partition_frame(hour_start, hour_end).write_parquet(path)

    partial_start = hour_start + timedelta(minutes=10)
    partial_end = hour_start + timedelta(minutes=20)
    result = audit_hour_partition_file(path, partial_start, partial_end)

    assert result.is_valid
    assert result.reason == "ok"
