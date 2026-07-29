from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_MIGRATIONS_PATH = Path("data/database/migrations")


def apply_migrations(
    connection: sqlite3.Connection,
    migrations_path: Path = DEFAULT_MIGRATIONS_PATH,
) -> list[str]:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    applied = {
        str(row[0])
        for row in connection.execute(
            "SELECT version FROM schema_migrations"
        ).fetchall()
    }
    completed: list[str] = []
    for migration in sorted(migrations_path.glob("*.sql")):
        version = migration.stem
        if version in applied:
            continue
        sql = migration.read_text(encoding="utf-8")
        connection.executescript(sql)
        connection.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, datetime.now(timezone.utc).isoformat()),
        )
        completed.append(version)
    connection.commit()
    return completed
