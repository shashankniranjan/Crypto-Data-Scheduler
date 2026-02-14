from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from binance_minute_lake.core.enums import PartitionStatus


@dataclass(frozen=True, slots=True)
class PartitionLedgerEntry:
    symbol: str
    day: str
    hour: int
    path: str
    row_count: int
    min_ts: str
    max_ts: str
    schema_hash: str
    content_hash: str
    status: PartitionStatus
    committed_at_utc: str


class SQLiteStateStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def db_path(self) -> Path:
        return self._db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watermark (
                    symbol TEXT PRIMARY KEY,
                    last_complete_minute_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS partitions (
                    symbol TEXT NOT NULL,
                    day TEXT NOT NULL,
                    hour INTEGER NOT NULL,
                    path TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    min_ts TEXT NOT NULL,
                    max_ts TEXT NOT NULL,
                    schema_hash TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    committed_at_utc TEXT NOT NULL,
                    PRIMARY KEY (symbol, day, hour)
                )
                """
            )
            conn.commit()

    def get_watermark(self, symbol: str) -> datetime | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT last_complete_minute_utc FROM watermark WHERE symbol = ?",
                (symbol,),
            ).fetchone()
        if row is None:
            return None
        return datetime.fromisoformat(row["last_complete_minute_utc"]).astimezone(UTC)

    def upsert_watermark(self, symbol: str, minute_utc: datetime) -> None:
        now_iso = datetime.now(tz=UTC).isoformat()
        minute_iso = minute_utc.astimezone(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO watermark(symbol, last_complete_minute_utc, updated_at_utc)
                VALUES (?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                  last_complete_minute_utc = excluded.last_complete_minute_utc,
                  updated_at_utc = excluded.updated_at_utc
                """,
                (symbol, minute_iso, now_iso),
            )
            conn.commit()

    def upsert_partition(self, entry: PartitionLedgerEntry) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO partitions(
                    symbol, day, hour, path, row_count, min_ts, max_ts,
                    schema_hash, content_hash, status, committed_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, day, hour) DO UPDATE SET
                    path = excluded.path,
                    row_count = excluded.row_count,
                    min_ts = excluded.min_ts,
                    max_ts = excluded.max_ts,
                    schema_hash = excluded.schema_hash,
                    content_hash = excluded.content_hash,
                    status = excluded.status,
                    committed_at_utc = excluded.committed_at_utc
                """,
                (
                    entry.symbol,
                    entry.day,
                    entry.hour,
                    entry.path,
                    entry.row_count,
                    entry.min_ts,
                    entry.max_ts,
                    entry.schema_hash,
                    entry.content_hash,
                    entry.status.value,
                    entry.committed_at_utc,
                ),
            )
            conn.commit()

    def latest_partition(self, symbol: str) -> PartitionLedgerEntry | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT symbol, day, hour, path, row_count, min_ts, max_ts,
                       schema_hash, content_hash, status, committed_at_utc
                FROM partitions
                WHERE symbol = ?
                ORDER BY day DESC, hour DESC
                LIMIT 1
                """,
                (symbol,),
            ).fetchone()
        if row is None:
            return None
        return PartitionLedgerEntry(
            symbol=row["symbol"],
            day=row["day"],
            hour=int(row["hour"]),
            path=row["path"],
            row_count=int(row["row_count"]),
            min_ts=row["min_ts"],
            max_ts=row["max_ts"],
            schema_hash=row["schema_hash"],
            content_hash=row["content_hash"],
            status=PartitionStatus(row["status"]),
            committed_at_utc=row["committed_at_utc"],
        )
