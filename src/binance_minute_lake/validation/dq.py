from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from binance_minute_lake.core.schema import canonical_column_names, hard_required_columns


class DataQualityError(RuntimeError):
    """Raised when mandatory data quality constraints fail."""


@dataclass(frozen=True, slots=True)
class DQResult:
    row_count: int
    min_ts: str
    max_ts: str


class DQValidator:
    def validate(self, frame: pl.DataFrame) -> DQResult:
        self._validate_columns(frame)
        self._validate_unique_timestamps(frame)
        self._validate_non_null_hard_required(frame)

        row_count = frame.height
        min_ts = ""
        max_ts = ""
        if row_count > 0:
            min_ts = str(frame.select(pl.col("timestamp").min()).item())
            max_ts = str(frame.select(pl.col("timestamp").max()).item())
        return DQResult(row_count=row_count, min_ts=min_ts, max_ts=max_ts)

    @staticmethod
    def _validate_columns(frame: pl.DataFrame) -> None:
        missing = sorted(set(canonical_column_names()) - set(frame.columns))
        if missing:
            raise DataQualityError(f"Missing canonical columns: {', '.join(missing)}")

    @staticmethod
    def _validate_unique_timestamps(frame: pl.DataFrame) -> None:
        duplicates = (
            frame.group_by("timestamp")
            .len()
            .filter(pl.col("len") > 1)
            .select(pl.len())
            .item()
        )
        if duplicates > 0:
            raise DataQualityError(f"Found {duplicates} duplicated timestamp buckets")

    @staticmethod
    def _validate_non_null_hard_required(frame: pl.DataFrame) -> None:
        hard_required = hard_required_columns()
        null_violations = []
        for column in hard_required:
            null_count = frame.select(pl.col(column).is_null().sum()).item()
            if null_count > 0:
                null_violations.append(f"{column}={null_count}")
        if null_violations:
            joined = ", ".join(null_violations)
            raise DataQualityError(f"HARD_REQUIRED null violations: {joined}")
