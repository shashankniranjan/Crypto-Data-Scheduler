# Binance Minute Lake

Production-grade Python ingestion pipeline for Binance USD-M Futures (`UM`) 1-minute canonical dataset, aligned with `/Users/shashankniranjan/Documents/New project/REQUIREMENTS_ADDENDUM.md`.

## Key features

- Mixed-frequency source normalization to 1-minute output rows.
- Temperature-band strategy:
  - Hot: WebSocket + REST
  - Warm: REST
  - Cold: Vision daily archives
- Idempotent partition writing with atomic commit semantics.
- SQLite state store for watermark and partition ledger.
- Typed schema registry containing all 58 canonical columns.
- Operational CLI for init, single run, and daemon poll loop.

## Project layout

- `/Users/shashankniranjan/Documents/New project/src/binance_minute_lake/core`: config, constants, schema metadata, logging
- `/Users/shashankniranjan/Documents/New project/src/binance_minute_lake/sources`: Vision and REST clients
- `/Users/shashankniranjan/Documents/New project/src/binance_minute_lake/transforms`: minute aggregation and normalization
- `/Users/shashankniranjan/Documents/New project/src/binance_minute_lake/state`: SQLite watermark + partition state
- `/Users/shashankniranjan/Documents/New project/src/binance_minute_lake/writer`: parquet atomic writer
- `/Users/shashankniranjan/Documents/New project/src/binance_minute_lake/pipeline`: orchestrator and poll loop
- `/Users/shashankniranjan/Documents/New project/src/binance_minute_lake/cli`: Typer CLI
- `/Users/shashankniranjan/Documents/New project/tests`: unit tests

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
bml init-state
bml run-once
```

## Operational commands

```bash
bml run-once
bml run-daemon --poll-seconds 60
bml show-watermark
bml backfill-years --years 5
bml backfill-range --start 2021-02-15T00:00:00+00:00 --end 2026-02-14T23:59:00+00:00
bml backfill-years --years 5 --max-missing-hours 24
```

Backfill commands now run a consistency audit over existing hour partitions and only repair missing/invalid hours.

## Airflow UI

Airflow is installed in a dedicated virtualenv and uses DAGs from `/Users/shashankniranjan/Documents/New project/airflow/dags`.

Start scheduler:

```bash
cd "/Users/shashankniranjan/Documents/New project"
./airflow/scripts/start_scheduler.sh
```

Start webserver in another terminal:

```bash
cd "/Users/shashankniranjan/Documents/New project"
./airflow/scripts/start_webserver.sh
```

Open [http://localhost:8080](http://localhost:8080).

Default login:

- `admin`
- `admin`

## Notes

- WebSocket collectors are optional in this baseline; live-only columns are populated as `NULL` when collector signals are unavailable.
- Vision download and REST fetch are implemented with explicit contracts, retries, and source provenance metadata hooks.
