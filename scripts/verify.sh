#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -z "${PFM_CONFIG:-}" && -f /etc/fieldmouse/station.toml ]]; then
    export PFM_CONFIG=/etc/fieldmouse/station.toml
fi
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
"$PYTHON" -m app.cli config validate
"$PYTHON" -m app.cli migrate
"$PYTHON" -m app.cli health --pretty
curl --fail --silent --show-error "http://127.0.0.1:${PFM_DASHBOARD_PORT:-8000}/health" >/dev/null
echo "Field Mouse verification passed."
