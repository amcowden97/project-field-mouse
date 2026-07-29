from __future__ import annotations

import sqlite3
import hashlib
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
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(schema_migrations)")
    }
    if "name" not in columns:
        connection.execute(
            "ALTER TABLE schema_migrations ADD COLUMN name TEXT NOT NULL DEFAULT ''"
        )
    if "checksum" not in columns:
        connection.execute(
            "ALTER TABLE schema_migrations ADD COLUMN checksum TEXT NOT NULL DEFAULT ''"
        )
    applied = {
        int(str(row[0]).split("_", 1)[0])
        for row in connection.execute(
            "SELECT version FROM schema_migrations"
        ).fetchall()
    }
    completed: list[str] = []
    for migration in sorted(migrations_path.glob("*.sql")):
        version_text, _, name = migration.stem.partition("_")
        version = int(version_text)
        if version in applied:
            continue
        sql = migration.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        try:
            connection.executescript(f"BEGIN IMMEDIATE;\n{sql}")
            connection.execute(
                """
                INSERT INTO schema_migrations (
                    version, name, checksum, applied_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    version,
                    name,
                    checksum,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        completed.append(migration.stem)
    return completed
