from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.utils.dates import days_ago

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BML_BIN = PROJECT_ROOT / ".venv" / "bin" / "bml"
INCREMENTAL_STATE_DB = PROJECT_ROOT / "state" / "incremental_state.sqlite"

with DAG(
    dag_id="bml_minute_incremental",
    description="Run Binance minute ingestion every minute",
    schedule="* * * * *",
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "data-eng",
        "depends_on_past": False,
        "retries": 2,
        "retry_delay": timedelta(seconds=20),
    },
    tags=["binance", "minute", "incremental"],
) as dag:
    ingest_minute = BashOperator(
        task_id="run_bml_once",
        bash_command=(
            f"set -euo pipefail; "
            f"cd '{PROJECT_ROOT}'; "
            f"BML_STATE_DB='{INCREMENTAL_STATE_DB}' "
            f"BML_BOOTSTRAP_LOOKBACK_MINUTES='10' "
            f"'{BML_BIN}' run-once --max-hours 1"
        ),
        execution_timeout=timedelta(minutes=20),
    )
