from __future__ import annotations

from datetime import UTC, datetime, timedelta


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def floor_to_minute(value: datetime) -> datetime:
    value_utc = value.astimezone(UTC)
    return value_utc.replace(second=0, microsecond=0)


def floor_to_hour(value: datetime) -> datetime:
    value_utc = value.astimezone(UTC)
    return value_utc.replace(minute=0, second=0, microsecond=0)


def iter_hours(start: datetime, end: datetime) -> list[datetime]:
    if end < start:
        return []
    hours: list[datetime] = []
    cursor = floor_to_hour(start)
    end_hour = floor_to_hour(end)
    while cursor <= end_hour:
        hours.append(cursor)
        cursor += timedelta(hours=1)
    return hours


def minute_epoch_ms(value: datetime) -> int:
    return int(floor_to_minute(value).timestamp() * 1000)
