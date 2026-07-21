#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

cd "$PROJECT_ROOT"

DATABASE_PATH="data/database/fieldmouse.db"

if [[ ! -f "$DATABASE_PATH" ]]; then
    echo "Database does not exist yet: $DATABASE_PATH"
    exit 1
fi

sqlite3 -header -column "$DATABASE_PATH" "
SELECT
    id,
    station_id,
    recorded_at,
    duration_seconds,
    file_size_bytes,
    processing_status,
    file_path
FROM recordings
ORDER BY recorded_at DESC;
"
