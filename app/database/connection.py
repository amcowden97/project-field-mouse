
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from app.config import FieldMouseConfig


class DatabaseError(RuntimeError):
    """Raised when a database operation fails."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect_database(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        connection = sqlite3.connect(database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection
    except sqlite3.Error as error:
        raise DatabaseError(
            f"Could not connect to database {database_path}: {error}"
        ) from error


def initialize_database(
    database_path: Path,
    schema_path: Path = Path("data/database/schema.sql"),
) -> None:
    if not schema_path.exists():
        raise DatabaseError(
            f"Database schema file not found: {schema_path}"
        )

    try:
        schema_sql = schema_path.read_text(encoding="utf-8")
    except OSError as error:
        raise DatabaseError(
            f"Could not read database schema: {error}"
        ) from error

    try:
        with closing(connect_database(database_path)) as connection:
            connection.executescript(schema_sql)
            connection.commit()
    except sqlite3.Error as error:
        raise DatabaseError(
            f"Could not initialize database: {error}"
        ) from error


def upsert_station(
    connection: sqlite3.Connection,
    config: FieldMouseConfig,
) -> None:
    try:
        connection.execute(
            """
            INSERT INTO stations (
                id,
                name,
                timezone,
                created_at
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                timezone = excluded.timezone
            """,
            (
                config.station.id,
                config.station.name,
                config.station.timezone,
                utc_now_iso(),
            ),
        )
    except sqlite3.Error as error:
        raise DatabaseError(
            f"Could not save station: {error}"
        ) from error


def insert_recording(
    connection: sqlite3.Connection,
    *,
    station_id: str,
    file_path: Path,
    recorded_at: str,
    duration_seconds: int,
    sample_rate: int,
    channels: int,
    sample_format: str,
    file_size_bytes: int,
) -> int:
    try:
        cursor = connection.execute(
            """
            INSERT INTO recordings (
                station_id,
                file_path,
                recorded_at,
                duration_seconds,
                sample_rate,
                channels,
                sample_format,
                file_size_bytes,
                processing_status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                station_id,
                str(file_path),
                recorded_at,
                duration_seconds,
                sample_rate,
                channels,
                sample_format,
                file_size_bytes,
                "pending",
                utc_now_iso(),
            ),
        )

        recording_id = cursor.lastrowid

        if recording_id is None:
            raise DatabaseError(
                "Recording was inserted, but no ID was returned."
            )

        return recording_id
    except sqlite3.IntegrityError as error:
        raise DatabaseError(
            f"Recording already exists or violates database rules: {error}"
        ) from error
    except sqlite3.Error as error:
        raise DatabaseError(
            f"Could not save recording: {error}"
        ) from error
