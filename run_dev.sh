#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
if [[ ! -f Settings.py ]]; then
  cp Settings_dev.py Settings.py
fi
if [[ ! -f .env ]]; then
  echo "Missing .env. Set RPW_DB_HOST, RPW_DB_USER, RPW_DB_PASSWORD and RPW_DB_NAME there." >&2
  exit 1
fi

set -a
source ./.env
set +a
export RPW_LOG_PATH="${RPW_LOG_PATH:-$PWD/logs}"
export RPW_LOG_LEVEL="${RPW_LOG_LEVEL:-INFO}"
exec .venv/bin/flask --app rpw run --debug --host=127.0.0.1 --port="${RPW_PORT:-55000}"
