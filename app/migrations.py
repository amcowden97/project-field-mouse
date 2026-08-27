"""Ordered, transactional SQLite migrations with automatic safety backups."""
from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.database.maintenance import backup_database

MIGRATIONS_DIRECTORY = Path(__file__).resolve().parents[1] / "data" / "database" / "migrations"


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path
    checksum: str


def _migration_checksum(content: bytes) -> str:
    """Hash SQL using repository-canonical LF line endings.

    Git may materialize a working tree with CRLF line endings on Windows.  The
    migration itself is unchanged in that case, so its immutable history hash
    must not depend on the platform that staged the release.
    """
    normalized = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def discover_migrations(directory: Path = MIGRATIONS_DIRECTORY) -> list[Migration]:
    migrations: list[Migration] = []
    for path in sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        prefix, _, label = path.stem.partition("_")
        content = path.read_bytes()
        migrations.append(Migration(int(prefix), label, path, _migration_checksum(content)))
    versions = [migration.version for migration in migrations]
    if versions != sorted(set(versions)):
        raise RuntimeError("Migration versions must be unique and ordered")
    return migrations


def _statements(sql: str) -> list[str]:
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            if buffer.strip():
                statements.append(buffer)
            buffer = ""
    if buffer.strip():
        raise RuntimeError("Migration ends with an incomplete SQL statement")
    return statements


def ensure_history(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL,
        applied_at TEXT NOT NULL)"""
    )
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(schema_migrations)")
    }
    if "checksum" not in columns:
        connection.execute("ALTER TABLE schema_migrations ADD COLUMN checksum TEXT NOT NULL DEFAULT ''")
    connection.commit()


def migration_history(database_path: Path) -> list[tuple]:
    with sqlite3.connect(database_path) as connection:
        ensure_history(connection)
        return connection.execute(
            "SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()


def migrate(
    database_path: Path,
    backup_directory: Path,
    directory: Path = MIGRATIONS_DIRECTORY,
) -> list[Migration]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        ensure_history(connection)
        applied = {
            row[0]: row[1]
            for row in connection.execute("SELECT version, checksum FROM schema_migrations")
        }
    migrations = discover_migrations(directory)
    for migration in migrations:
        if migration.version in applied and applied[migration.version] not in {"", migration.checksum}:
            raise RuntimeError(f"Applied migration {migration.version} was modified")
    pending = [item for item in migrations if item.version not in applied]
    if not pending:
        return []
    if database_path.stat().st_size:
        backup_database(database_path, backup_directory)
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        ensure_history(connection)
        for migration in pending:
            try:
                connection.execute("BEGIN IMMEDIATE")
                index_creation_ms = 0.0
                for statement in _statements(migration.path.read_text(encoding="utf-8")):
                    started = time.perf_counter()
                    connection.execute(statement)
                    if statement.lstrip().upper().startswith(
                        ("CREATE INDEX", "CREATE UNIQUE INDEX")
                    ):
                        index_creation_ms += (time.perf_counter() - started) * 1000
                if migration.version == 6:
                    from app.science.migration import backfill_recording_lifecycle

                    backfill_recording_lifecycle(
                        connection,
                        migration_version=migration.version,
                        index_creation_ms=index_creation_ms,
                    )
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
                    (migration.version, migration.name, migration.checksum,
                     datetime.now(timezone.utc).isoformat()),
                )
                if connection.execute("PRAGMA foreign_key_check").fetchone():
                    raise RuntimeError("foreign key validation failed")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
    return pending
