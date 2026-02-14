from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VisionObject:
    stream: str
    symbol: str
    trade_date: date
    url: str
    exists: bool


_INTERVAL_STREAMS: Final[set[str]] = {
    "klines",
    "markPriceKlines",
    "indexPriceKlines",
    "premiumIndexKlines",
}

_STREAM_TO_PATTERN: Final[dict[str, tuple[str, str]]] = {
    "klines": ("klines/{symbol}/{interval}/", "{symbol}-{interval}-{date}.zip"),
    "aggTrades": ("aggTrades/{symbol}/", "{symbol}-aggTrades-{date}.zip"),
    "bookTicker": ("bookTicker/{symbol}/", "{symbol}-bookTicker-{date}.zip"),
    "bookDepth": ("bookDepth/{symbol}/", "{symbol}-bookDepth-{date}.zip"),
    "markPriceKlines": (
        "markPriceKlines/{symbol}/{interval}/",
        "{symbol}-markPriceKlines-{interval}-{date}.zip",
    ),
    "indexPriceKlines": (
        "indexPriceKlines/{symbol}/{interval}/",
        "{symbol}-indexPriceKlines-{interval}-{date}.zip",
    ),
    "premiumIndexKlines": (
        "premiumIndexKlines/{symbol}/{interval}/",
        "{symbol}-premiumIndexKlines-{interval}-{date}.zip",
    ),
    "metrics": ("metrics/{symbol}/", "{symbol}-metrics-{date}.zip"),
    "trades": ("trades/{symbol}/", "{symbol}-trades-{date}.zip"),
}


class VisionClient:
    def __init__(self, base_url: str, timeout_seconds: int = 20) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        self._client.close()

    def expected_filename(self, stream: str, symbol: str, trade_date: date, interval: str = "1m") -> str:
        _, file_pattern = self._lookup_patterns(stream)
        return file_pattern.format(symbol=symbol.upper(), interval=interval, date=trade_date.isoformat())

    def build_daily_zip_url(self, stream: str, symbol: str, trade_date: date, interval: str = "1m") -> str:
        folder_pattern, _ = self._lookup_patterns(stream)
        folder = folder_pattern.format(symbol=symbol.upper(), interval=interval)
        filename = self.expected_filename(stream=stream, symbol=symbol, trade_date=trade_date, interval=interval)
        return f"{self._base_url}/{folder}{filename}"

    def object_status(
        self,
        stream: str,
        symbol: str,
        trade_date: date,
        interval: str = "1m",
    ) -> VisionObject:
        url = self.build_daily_zip_url(stream=stream, symbol=symbol, trade_date=trade_date, interval=interval)
        exists = self.exists(url)
        return VisionObject(
            stream=stream,
            symbol=symbol.upper(),
            trade_date=trade_date,
            url=url,
            exists=exists,
        )

    def exists(self, url: str) -> bool:
        response = self._client.head(url)
        if response.status_code == 200:
            return True
        if response.status_code in {403, 405}:
            fallback = self._client.get(url, headers={"Range": "bytes=0-0"})
            return fallback.status_code in {200, 206}
        return False

    def download_zip(self, url: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._client.stream("GET", url) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    handle.write(chunk)
        logger.info("downloaded vision object", extra={"url": url, "path": str(destination)})
        return destination

    @staticmethod
    def _lookup_patterns(stream: str) -> tuple[str, str]:
        if stream not in _STREAM_TO_PATTERN:
            supported = ", ".join(sorted(_STREAM_TO_PATTERN))
            raise ValueError(f"Unsupported Vision stream '{stream}'. Supported: {supported}")
        return _STREAM_TO_PATTERN[stream]

    @staticmethod
    def requires_interval(stream: str) -> bool:
        return stream in _INTERVAL_STREAMS
