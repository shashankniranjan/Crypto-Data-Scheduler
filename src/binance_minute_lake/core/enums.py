from __future__ import annotations

from enum import Enum


class SupportClass(str, Enum):
    HARD_REQUIRED = "HARD_REQUIRED"
    BACKFILL_AVAILABLE = "BACKFILL_AVAILABLE"
    LIVE_ONLY = "LIVE_ONLY"
    OPTIONAL = "OPTIONAL"


class IngestionBand(str, Enum):
    HOT = "HOT"
    WARM = "WARM"
    COLD = "COLD"


class PartitionStatus(str, Enum):
    STAGED = "STAGED"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"
