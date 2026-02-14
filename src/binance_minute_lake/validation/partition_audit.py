from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from binance_minute_lake.core.schema import hard_required_columns


@dataclass(frozen=True, slots=True)
class PartitionAuditResult:
    is_valid: bool
    reason: str


def audit_hour_partition_file(
    path: Path,
    expected_start: datetime,
    expected_end: datetime,
) -> PartitionAuditResult:
    expected_start_utc = expected_start.astimezone(UTC).replace(second=0, microsecond=0)
    expected_end_utc = expected_end.astimezone(UTC).replace(second=0, microsecond=0)
    if expected_end_utc < expected_start_utc:
        return PartitionAuditResult(is_valid=False, reason="invalid_expected_range")

    if not path.exists():
        return PartitionAuditResult(is_valid=False, reason="missing_file")

    try:
        schema = pl.read_parquet_schema(path)
    except Exception as exc:
        return PartitionAuditResult(is_valid=False, reason=f"unreadable_parquet:{exc.__class__.__name__}")

    required_cols = set(hard_required_columns())
    missing_cols = sorted(required_cols - set(schema.keys()))
    if missing_cols:
        return PartitionAuditResult(
            is_valid=False,
            reason=f"missing_columns:{','.join(missing_cols)}",
        )

    try:
        frame = pl.read_parquet(path, columns=sorted(required_cols))
    except Exception as exc:
        return PartitionAuditResult(is_valid=False, reason=f"read_error:{exc.__class__.__name__}")

    timestamps = frame.get_column("timestamp").sort()
    row_count = timestamps.len()

    if timestamps.n_unique() != row_count:
        return PartitionAuditResult(is_valid=False, reason="duplicate_timestamps")

    if row_count == 0:
        return PartitionAuditResult(is_valid=False, reason="empty_partition")

    expected_rows = int((expected_end_utc - expected_start_utc).total_seconds() // 60) + 1
    in_window = frame.filter(
        (pl.col("timestamp") >= expected_start_utc) & (pl.col("timestamp") <= expected_end_utc)
    ).sort("timestamp")
    in_window_timestamps = in_window.get_column("timestamp")

    if in_window.height != expected_rows:
        return PartitionAuditResult(
            is_valid=False,
            reason=(
                "row_count_mismatch:"
                f"expected={expected_rows}:actual={in_window.height}:"
                f"window={expected_start_utc.isoformat()}..{expected_end_utc.isoformat()}"
            ),
        )

    expected_series = pl.datetime_range(
        start=expected_start_utc,
        end=expected_end_utc,
        interval="1m",
        eager=True,
        time_zone="UTC",
    )
    if not in_window_timestamps.equals(expected_series):
        return PartitionAuditResult(is_valid=False, reason="timestamp_gap_or_order_error")

    null_violations: list[str] = []
    for column in sorted(required_cols):
        null_count = in_window.get_column(column).null_count()
        if null_count > 0:
            null_violations.append(f"{column}:{null_count}")
    if null_violations:
        return PartitionAuditResult(
            is_valid=False,
            reason=f"hard_required_nulls:{','.join(null_violations)}",
        )

    return PartitionAuditResult(is_valid=True, reason="ok")
