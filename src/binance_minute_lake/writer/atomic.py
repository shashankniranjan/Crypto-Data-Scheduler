from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from binance_minute_lake.core.enums import PartitionStatus
from binance_minute_lake.core.schema import canonical_column_names, schema_hash_input
from binance_minute_lake.state.store import PartitionLedgerEntry, SQLiteStateStore
from binance_minute_lake.validation.dq import DQValidator


class AtomicParquetWriter:
    def __init__(self, root_dir: Path, state_store: SQLiteStateStore, validator: DQValidator) -> None:
        self._root_dir = root_dir
        self._state_store = state_store
        self._validator = validator

    def write_hour_partition(self, symbol: str, hour_start: datetime, frame: pl.DataFrame) -> Path:
        symbol_upper = symbol.upper()
        final_path = self._partition_path(symbol_upper, hour_start)
        final_path.parent.mkdir(parents=True, exist_ok=True)

        effective_frame = frame
        if final_path.exists():
            existing_frame = pl.read_parquet(final_path)
            effective_frame = self._merge_partition_frames(existing_frame=existing_frame, new_frame=frame)

        dq_result = self._validator.validate(effective_frame)

        tmp_dir = self._root_dir / ".tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / f"{uuid.uuid4().hex}.parquet"

        effective_frame.write_parquet(tmp_path, compression="zstd", statistics=True)
        tmp_path.replace(final_path)

        schema_hash = self._schema_hash()
        content_hash = self._file_hash(final_path)

        entry = PartitionLedgerEntry(
            symbol=symbol_upper,
            day=hour_start.strftime("%Y-%m-%d"),
            hour=hour_start.hour,
            path=str(final_path),
            row_count=dq_result.row_count,
            min_ts=dq_result.min_ts,
            max_ts=dq_result.max_ts,
            schema_hash=schema_hash,
            content_hash=content_hash,
            status=PartitionStatus.COMMITTED,
            committed_at_utc=datetime.now(tz=UTC).isoformat(),
        )
        self._state_store.upsert_partition(entry)
        return final_path

    @staticmethod
    def _merge_partition_frames(existing_frame: pl.DataFrame, new_frame: pl.DataFrame) -> pl.DataFrame:
        merged = pl.concat([existing_frame, new_frame], how="vertical")
        merged = (
            merged.sort("timestamp")
            .unique(subset=["timestamp"], keep="last")
            .sort("timestamp")
            .select(canonical_column_names())
        )
        return merged

    def _partition_path(self, symbol: str, hour_start: datetime) -> Path:
        return (
            self._root_dir
            / "futures"
            / "um"
            / "minute"
            / f"symbol={symbol}"
            / f"year={hour_start:%Y}"
            / f"month={hour_start:%m}"
            / f"day={hour_start:%d}"
            / f"hour={hour_start:%H}"
            / "part.parquet"
        )

    @staticmethod
    def _schema_hash() -> str:
        digest = hashlib.sha256()
        digest.update(schema_hash_input().encode("utf-8"))
        return digest.hexdigest()

    @staticmethod
    def _file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
