#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
"$PYTHON" -m app.database.maintenance check
"$PYTHON" -m app.system.health_check --pretty
curl --fail --silent --show-error "http://127.0.0.1:${PFM_DASHBOARD_PORT:-8000}/health" >/dev/null
echo "Field Mouse verification passed."
