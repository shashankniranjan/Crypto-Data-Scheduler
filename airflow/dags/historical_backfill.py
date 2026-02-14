from __future__ import annotations

import os
import subprocess
from datetime import timedelta
from pathlib import Path

from airflow import DAG
from airflow.decorators import task
from airflow.models.param import Param
from airflow.utils.dates import days_ago

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BML_BIN = PROJECT_ROOT / ".venv" / "bin" / "bml"
BACKFILL_STATE_DB = PROJECT_ROOT / "state" / "backfill_state.sqlite"

with DAG(
    dag_id="bml_historical_backfill",
    description="Manual backfill for Binance minute lake",
    schedule=None,
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=24),
    params={
        "mode": Param("years", enum=["years", "range"]),
        "years": Param(5, type="integer", minimum=1, maximum=10),
        "start": Param("2021-02-24T00:00:00+00:00", type="string"),
        "end": Param("2026-01-01T00:00:00+00:00", type="string"),
        "sleep_seconds": Param(0.2, type="number", minimum=0),
        "max_missing_hours": Param(None, ["null", "integer"]),
    },
    tags=["binance", "backfill", "manual"],
) as dag:
    @task(task_id="run_backfill")
    def run_backfill(**context: object) -> None:
        params: dict[str, object] = context["params"]  # type: ignore[index]

        mode = str(params.get("mode", "years"))
        sleep_seconds = float(params.get("sleep_seconds", 0.2))

        base_cmd = [str(BML_BIN)]

        max_missing_hours_value = params.get("max_missing_hours")
        max_missing_hours = (
            int(max_missing_hours_value)
            if max_missing_hours_value not in (None, "")
            else None
        )

        if mode == "range":
            start = str(params["start"])
            end = str(params["end"])
            command = [
                *base_cmd,
                "backfill-range",
                "--start",
                start,
                "--end",
                end,
                "--sleep-seconds",
                str(sleep_seconds),
            ]
        else:
            years = int(params.get("years", 5))
            command = [
                *base_cmd,
                "backfill-years",
                "--years",
                str(years),
                "--sleep-seconds",
                str(sleep_seconds),
            ]

        if max_missing_hours is not None:
            command.extend(["--max-missing-hours", str(max_missing_hours)])

        env = os.environ.copy()
        env["BML_STATE_DB"] = str(BACKFILL_STATE_DB)
        subprocess.run(command, check=True, cwd=PROJECT_ROOT, env=env)  # noqa: S603

    run_backfill()
