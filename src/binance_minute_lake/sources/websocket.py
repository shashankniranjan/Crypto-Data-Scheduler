from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LiveMinuteFeatures:
    timestamp_ms: int
    event_time: int | None = None
    arrival_time: int | None = None
    latency_engine: int | None = None
    latency_network: int | None = None
    update_id_start: int | None = None
    update_id_end: int | None = None
    price_impact_100k: float | None = None
    predicted_funding: float | None = None
    next_funding_time: int | None = None


class LiveCollector:
    """Live collector contract.

    Implementations are optional in baseline mode. When no collector is provided,
    all live-only columns remain NULL by schema contract.
    """

    def snapshot_for_minute(self, minute_timestamp_ms: int) -> LiveMinuteFeatures | None:
        return None
