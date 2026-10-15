from __future__ import annotations

import sqlite3
import json
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from app.config import PROJECT_ROOT, FieldMouseConfig
from app.database.migrations import apply_migrations
from app.synchronization import new_recording_identity, normalize_station_uuid
from app.version import __version__


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
        raise DatabaseError(f"Could not connect to database {database_path}: {error}") from error


def initialize_database(
    database_path: Path,
    schema_path: Path = PROJECT_ROOT / "data" / "database" / "schema.sql",
) -> None:
    if not schema_path.exists():
        raise DatabaseError(f"Database schema file not found: {schema_path}")

    try:
        schema_sql = schema_path.read_text(encoding="utf-8")
    except OSError as error:
        raise DatabaseError(f"Could not read database schema: {error}") from error

    try:
        with closing(connect_database(database_path)) as connection:
            connection.executescript(schema_sql)
            apply_migrations(connection)
            connection.commit()
    except sqlite3.Error as error:
        raise DatabaseError(f"Could not initialize database: {error}") from error


def upsert_station(
    connection: sqlite3.Connection,
    config: FieldMouseConfig,
) -> None:
    try:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(stations)").fetchall()
        }
        if "station_uuid" in columns:
            configured_uuid = normalize_station_uuid(config.station.uuid)
            existing = connection.execute(
                "SELECT station_uuid FROM stations WHERE id = ?",
                (config.station.id,),
            ).fetchone()
            existing_uuid = (
                normalize_station_uuid(str(existing["station_uuid"]))
                if existing is not None and existing["station_uuid"]
                else ""
            )
            if configured_uuid and existing_uuid and configured_uuid != existing_uuid:
                raise DatabaseError(
                    "Configured station UUID does not match the durable database identity"
                )
            connection.execute(
                """
                INSERT INTO stations (
                    id, name, timezone, created_at, station_uuid, hardware_version,
                    software_version, deployment_date, location_name, latitude,
                    longitude, capabilities
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    timezone = excluded.timezone,
                    station_uuid = COALESCE(stations.station_uuid, excluded.station_uuid),
                    hardware_version = excluded.hardware_version,
                    software_version = excluded.software_version,
                    deployment_date = excluded.deployment_date,
                    location_name = excluded.location_name,
                    latitude = excluded.latitude,
                    longitude = excluded.longitude,
                    capabilities = excluded.capabilities
                """,
                (
                    config.station.id,
                    config.station.name,
                    config.station.timezone,
                    utc_now_iso(),
                    configured_uuid or None,
                    config.station.hardware_version,
                    __version__,
                    config.station.deployment_date or None,
                    config.station.location_name or None,
                    config.station.latitude,
                    config.station.longitude,
                    json.dumps(config.station.capabilities),
                ),
            )
            return
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
        raise DatabaseError(f"Could not save station: {error}") from error


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
    recording_identity: str | None = None,
    content_sha256: str | None = None,
    station_uuid: str | None = None,
) -> int:
    identity = recording_identity or new_recording_identity()
    normalized_station_uuid = (
        normalize_station_uuid(station_uuid, required=True) if station_uuid is not None else None
    )
    if normalized_station_uuid is not None and content_sha256 is None:
        raise DatabaseError("A content SHA-256 is required before creating synchronization intent")
    savepoint = "insert_recording_with_sync_intent"
    try:
        connection.execute(f"SAVEPOINT {savepoint}")
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(recordings)").fetchall()
        }
        insert_columns = [
            "station_id",
            "file_path",
            "recorded_at",
            "duration_seconds",
            "sample_rate",
            "channels",
            "sample_format",
            "file_size_bytes",
            "processing_status",
        ]
        values: list[object] = [
            station_id,
            str(file_path),
            recorded_at,
            duration_seconds,
            sample_rate,
            channels,
            sample_format,
            file_size_bytes,
            "pending",
        ]
        if "recording_identity" in columns:
            insert_columns.append("recording_identity")
            values.append(identity)
        if "content_sha256" in columns:
            insert_columns.append("content_sha256")
            values.append(content_sha256)
        elif normalized_station_uuid is not None:
            raise DatabaseError("Station synchronization requires database migration 0011")
        insert_columns.append("created_at")
        values.append(utc_now_iso())
        placeholders = ", ".join("?" for _ in values)
        cursor = connection.execute(
            f"INSERT INTO recordings ({', '.join(insert_columns)}) VALUES ({placeholders})",
            values,
        )

        recording_id = cursor.lastrowid

        if recording_id is None:
            raise DatabaseError("Recording was inserted, but no ID was returned.")

        if "source_availability" in columns:
            from app.science.recordings import SourceAvailability, set_source_availability

            set_source_availability(
                connection,
                recording_id=int(recording_id),
                availability=SourceAvailability.AVAILABLE,
                reason_code="RECORDER_CREATED_SOURCE",
                authorized_by="RECORDER",
                authorization_reference=str(file_path),
                operation_id=f"recorder-create-{recording_id}",
            )

        if normalized_station_uuid is not None:
            now = utc_now_iso()
            connection.execute(
                """
                INSERT INTO station_sync_outbox (
                    recording_id, recording_identity, station_uuid, state,
                    attempt_count, created_at, updated_at
                ) VALUES (?, ?, ?, 'PENDING', 0, ?, ?)
                """,
                (
                    int(recording_id),
                    identity,
                    normalized_station_uuid,
                    now,
                    now,
                ),
            )

        connection.execute(f"RELEASE SAVEPOINT {savepoint}")

        return int(recording_id)
    except (sqlite3.Error, DatabaseError, ValueError) as error:
        try:
            connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            connection.execute(f"RELEASE SAVEPOINT {savepoint}")
        except sqlite3.Error:
            pass
        if isinstance(error, DatabaseError):
            raise
        if isinstance(error, ValueError):
            raise DatabaseError(str(error)) from error
        if isinstance(error, sqlite3.IntegrityError):
            raise DatabaseError(
                f"Recording already exists or violates database rules: {error}"
            ) from error
        raise DatabaseError(f"Could not save recording: {error}") from error
