from __future__ import annotations

from datetime import UTC, datetime, timedelta

import typer
from rich.console import Console

from binance_minute_lake.core.config import Settings
from binance_minute_lake.core.logging import configure_logging
from binance_minute_lake.core.time_utils import floor_to_minute, utc_now
from binance_minute_lake.pipeline.orchestrator import MinuteIngestionPipeline
from binance_minute_lake.sources.metrics_inspector import MetricsZipInspector
from binance_minute_lake.sources.vision import VisionClient
from binance_minute_lake.state.store import SQLiteStateStore

app = typer.Typer(help="Binance minute lake ingestion CLI")
console = Console()


def _parse_utc_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@app.command("init-state")
def init_state() -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    store = SQLiteStateStore(settings.state_db)
    store.initialize()
    console.print(f"State initialized at [bold]{settings.state_db}[/bold]")


@app.command("show-watermark")
def show_watermark(symbol: str | None = None) -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    store = SQLiteStateStore(settings.state_db)
    store.initialize()
    symbol_value = (symbol or settings.symbol).upper()
    watermark = store.get_watermark(symbol_value)
    if watermark is None:
        console.print(f"No watermark found for {symbol_value}")
        return
    console.print(f"Watermark[{symbol_value}] = [bold]{watermark.isoformat()}[/bold]")


@app.command("run-once")
def run_once(
    at: str | None = typer.Option(default=None, help="Optional UTC ISO datetime"),
    max_hours: int | None = typer.Option(
        default=None,
        min=1,
        max=24,
        help="Optional cap on hours processed in this invocation",
    ),
) -> None:
    settings = Settings()
    configure_logging(settings.log_level)

    run_at: datetime | None = None
    if at is not None:
        run_at = datetime.fromisoformat(at)
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=UTC)

    pipeline = MinuteIngestionPipeline(settings=settings)
    try:
        summary = pipeline.run_once(now=run_at, max_hours=max_hours)
    finally:
        pipeline.close()

    console.print(
        "Run complete: "
        f"symbol={summary.symbol}, "
        f"partitions={summary.partitions_committed}, "
        f"watermark_before={summary.watermark_before.isoformat()}, "
        f"watermark_after={summary.watermark_after.isoformat()}, "
        f"target={summary.target_horizon.isoformat()}"
    )


@app.command("run-daemon")
def run_daemon(
    poll_seconds: int = typer.Option(default=60, min=5, help="Polling interval in seconds"),
) -> None:
    settings = Settings()
    configure_logging(settings.log_level)

    pipeline = MinuteIngestionPipeline(settings=settings)
    try:
        pipeline.run_daemon(poll_seconds=poll_seconds)
    finally:
        pipeline.close()


@app.command("inspect-metrics-columns")
def inspect_metrics_columns(
    trade_date: str = typer.Option(help="Date in YYYY-MM-DD format"),
    symbol: str | None = typer.Option(default=None),
) -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    symbol_value = (symbol or settings.symbol).upper()
    parsed_date = datetime.strptime(trade_date, "%Y-%m-%d").date()

    vision = VisionClient(base_url=settings.vision_base_url)
    try:
        url = vision.build_daily_zip_url("metrics", symbol_value, parsed_date)
        destination = settings.root_dir / ".cache" / f"{symbol_value}-metrics-{trade_date}.zip"
        vision.download_zip(url=url, destination=destination)
    finally:
        vision.close()

    columns = MetricsZipInspector.list_columns(destination)
    console.print(f"Metrics columns ({len(columns)}):")
    for column in columns:
        console.print(f" - {column}")


@app.command("backfill-range")
def backfill_range(
    start: str = typer.Option(help="Start datetime in ISO format (UTC if no timezone)"),
    end: str | None = typer.Option(
        default=None,
        help="End datetime in ISO format (default: now-safety-lag)",
    ),
    sleep_seconds: float = typer.Option(
        default=0.0,
        min=0.0,
        max=10.0,
        help="Optional sleep between repaired hours to reduce API pressure",
    ),
    max_missing_hours: int | None = typer.Option(
        default=None,
        min=1,
        help="Optional cap for number of missing/invalid hours repaired in this invocation",
    ),
) -> None:
    settings = Settings()
    configure_logging(settings.log_level)

    start_utc = floor_to_minute(_parse_utc_datetime(start))
    if end is None:
        end_utc = floor_to_minute(utc_now() - timedelta(minutes=settings.safety_lag_minutes))
    else:
        end_utc = floor_to_minute(_parse_utc_datetime(end))

    if end_utc < start_utc:
        raise typer.BadParameter("end must be >= start")

    pipeline = MinuteIngestionPipeline(settings=settings)
    try:
        summary = pipeline.run_consistency_backfill(
            start=start_utc,
            end=end_utc,
            now_for_band=utc_now(),
            sleep_seconds=sleep_seconds,
            max_missing_hours=max_missing_hours,
        )
    finally:
        pipeline.close()

    console.print(
        "Backfill consistency: "
        f"hours_scanned={summary.hours_scanned}, "
        f"issues_found={summary.issues_found}, "
        f"issues_targeted={summary.issues_targeted}, "
        f"hours_repaired={summary.hours_repaired}, "
        f"hours_failed={summary.hours_failed}, "
        f"issues_remaining={summary.issues_remaining}"
    )

    if max_missing_hours is None and summary.issues_remaining > 0:
        raise typer.Exit(code=1)


@app.command("backfill-years")
def backfill_years(
    years: int = typer.Option(default=5, min=1, max=10),
    sleep_seconds: float = typer.Option(default=0.0, min=0.0, max=10.0),
    max_missing_hours: int | None = typer.Option(default=None, min=1),
) -> None:
    settings = Settings()
    configure_logging(settings.log_level)

    end_utc = floor_to_minute(utc_now() - timedelta(minutes=settings.safety_lag_minutes))
    start_utc = floor_to_minute(end_utc - timedelta(days=365 * years))

    pipeline = MinuteIngestionPipeline(settings=settings)
    try:
        summary = pipeline.run_consistency_backfill(
            start=start_utc,
            end=end_utc,
            now_for_band=utc_now(),
            sleep_seconds=sleep_seconds,
            max_missing_hours=max_missing_hours,
        )
    finally:
        pipeline.close()

    console.print(
        "Backfill consistency: "
        f"hours_scanned={summary.hours_scanned}, "
        f"issues_found={summary.issues_found}, "
        f"issues_targeted={summary.issues_targeted}, "
        f"hours_repaired={summary.hours_repaired}, "
        f"hours_failed={summary.hours_failed}, "
        f"issues_remaining={summary.issues_remaining}"
    )

    if max_missing_hours is None and summary.issues_remaining > 0:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
