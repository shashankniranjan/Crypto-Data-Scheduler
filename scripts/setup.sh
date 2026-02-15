#!/usr/bin/env bash
set -euo pipefail

# Project bootstrap: create venv, install deps, optional daemon start.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

echo "==> Using python: $PYTHON_BIN"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "==> Creating virtualenv at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "==> Upgrading pip"
python -m pip install --upgrade pip

echo "==> Installing project (editable) with dev extras"
python -m pip install -e .[dev]

echo "==> Installing duckdb client (for DuckDB materialization)"
python -m pip install duckdb

if [ -f ".env.example" ] && [ ! -f ".env" ]; then
  echo "==> Creating .env from .env.example"
  cp .env.example .env
fi

echo "==> Setup complete."
echo "Useful commands:"
echo "  PYTHONPATH=src bml run-once"
echo "  PYTHONPATH=src bml run-forever"
echo "  PYTHONPATH=src bml materialize-duckdb --db-path data/minute.duckdb"

read -r -p "Start the run-forever daemon now? [y/N] " REPLY
case "$REPLY" in
  [yY][eE][sS]|[yY])
    echo "==> Starting daemon (Ctrl+C to stop)..."
    PYTHONPATH=src bml run-forever
    ;;
  *)
    echo "==> Skipping daemon start."
    ;;
esac
