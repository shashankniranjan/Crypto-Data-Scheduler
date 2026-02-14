# Airflow Integration

This directory runs the ingestion pipeline through Apache Airflow.

## DAGs

- `bml_minute_incremental`: runs every minute and executes `bml run-once`
- `bml_historical_backfill`: manual DAG for consistency backfills (`years` or explicit `range`) that repair missing/invalid hour partitions

Backfill DAG params:

- `mode`: `years` or `range`
- `years`: used when `mode=years`
- `start` / `end`: used when `mode=range`
- `sleep_seconds`: throttle between repaired hours
- `max_missing_hours`: optional cap; `null` means repair all detected gaps in one run

## Layout

- `airflow/dags/`: DAG definitions
- `airflow/home/`: `AIRFLOW_HOME` (metadata DB, config)
- `airflow/logs/`: scheduler/webserver/worker logs

## Quick start

```bash
cd "/Users/shashankniranjan/Documents/New project"
source .venv-airflow/bin/activate
export AIRFLOW_HOME="/Users/shashankniranjan/Documents/New project/airflow/home"
export AIRFLOW__CORE__DAGS_FOLDER="/Users/shashankniranjan/Documents/New project/airflow/dags"
export AIRFLOW__CORE__LOAD_EXAMPLES="False"
airflow db migrate
airflow users create --username admin --firstname Admin --lastname User --role Admin --email admin@example.com --password admin
airflow scheduler
```

In another terminal:

```bash
cd "/Users/shashankniranjan/Documents/New project"
source .venv-airflow/bin/activate
export AIRFLOW_HOME="/Users/shashankniranjan/Documents/New project/airflow/home"
export AIRFLOW__CORE__DAGS_FOLDER="/Users/shashankniranjan/Documents/New project/airflow/dags"
export AIRFLOW__CORE__LOAD_EXAMPLES="False"
airflow webserver --port 8080
```

Open [http://localhost:8080](http://localhost:8080).

Default login created during install:

- username: `admin`
- password: `admin`
