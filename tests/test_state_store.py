from datetime import UTC, datetime
from pathlib import Path

from binance_minute_lake.core.enums import PartitionStatus
from binance_minute_lake.state.store import PartitionLedgerEntry, SQLiteStateStore


def test_watermark_roundtrip(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state.sqlite")
    store.initialize()

    ts = datetime(2026, 1, 15, 10, 2, tzinfo=UTC)
    store.upsert_watermark("BTCUSDT", ts)
    read_back = store.get_watermark("BTCUSDT")

    assert read_back == ts


def test_partition_upsert_and_latest(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path / "state.sqlite")
    store.initialize()

    entry = PartitionLedgerEntry(
        symbol="BTCUSDT",
        day="2026-01-15",
        hour=10,
        path="/tmp/part.parquet",
        row_count=60,
        min_ts="2026-01-15T10:00:00+00:00",
        max_ts="2026-01-15T10:59:00+00:00",
        schema_hash="abc",
        content_hash="def",
        status=PartitionStatus.COMMITTED,
        committed_at_utc="2026-01-15T11:00:00+00:00",
    )
    store.upsert_partition(entry)

    latest = store.latest_partition("BTCUSDT")
    assert latest is not None
    assert latest.hour == 10
    assert latest.status == PartitionStatus.COMMITTED
