#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/shashankniranjan/Documents/New project"
source "$ROOT/.venv-airflow/bin/activate"
export AIRFLOW_HOME="$ROOT/airflow/home"
export AIRFLOW__CORE__DAGS_FOLDER="$ROOT/airflow/dags"
export AIRFLOW__CORE__LOAD_EXAMPLES="False"
exec airflow webserver --port 8080
