"""Local identity primitives for the future Station-to-Server boundary.

This module intentionally contains no transport, retry, or acknowledgement
behavior.  It only owns durable identifier validation/generation and the
historical identity migration used by migration 0011.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_station_uuid(value: str, *, required: bool = False) -> str:
    """Return the canonical Station UUID, allowing absence when sync is off."""
    candidate = value.strip()
    if not candidate:
        if required:
            raise ValueError("station UUID is required for synchronization")
        return ""
    try:
        parsed = uuid.UUID(candidate)
    except (AttributeError, ValueError) as error:
        raise ValueError("station UUID must be a valid UUID") from error
    if parsed.int == 0:
        raise ValueError("station UUID cannot be the nil UUID")
    return str(parsed)


def new_recording_identity() -> str:
    """Generate an opaque distributed identity supported by Python 3.11+."""
    return str(uuid.uuid4())


def _uuid_or_none(value: object) -> uuid.UUID | None:
    try:
        parsed = uuid.UUID(str(value))
    except (AttributeError, ValueError):
        return None
    return None if parsed.int == 0 else parsed


def backfill_station_sync_identities(
    connection: sqlite3.Connection,
    *,
    migration_version: int,
) -> dict[str, int | float]:
    """Assign recording UUIDs without reading media or inventing Station UUIDs.

    Existing valid Station UUIDs are retained but missing/invalid values are
    never invented by a database-only migration: the Station configuration is
    the authority for that identity.  Historical Recording identities use
    UUIDv5 within a valid Station namespace or a one-time UUIDv4 when no such
    namespace exists.  A rerun therefore preserves every assigned value.
    """
    started = time.perf_counter()
    station_uuids_assigned = 0
    recording_identities_assigned = 0

    stations = connection.execute("SELECT id, station_uuid FROM stations ORDER BY id").fetchall()
    station_namespaces: dict[str, uuid.UUID] = {}
    for station_id, raw_uuid in stations:
        parsed = _uuid_or_none(raw_uuid)
        if parsed is not None:
            station_namespaces[str(station_id)] = parsed

    rows = connection.execute(
        "SELECT id, station_id, recording_identity FROM recordings ORDER BY id"
    ).fetchall()
    for recording_id, station_id, raw_identity in rows:
        if _uuid_or_none(raw_identity) is not None:
            continue
        namespace = station_namespaces.get(str(station_id))
        identity = (
            uuid.uuid5(
                namespace,
                f"project-field-mouse-recording:{int(recording_id)}",
            )
            if namespace is not None
            else uuid.uuid4()
        )
        connection.execute(
            "UPDATE recordings SET recording_identity = ? WHERE id = ?",
            (str(identity), recording_id),
        )
        recording_identities_assigned += 1

    # The legacy trigger derived identity from mutable local/database details.
    # This replacement is only a safety net for direct SQL writers; application
    # writes supply a UUIDv4 explicitly before persistence completes.
    trigger_statements = (
        """
        CREATE TRIGGER recordings_assign_identity
        AFTER INSERT ON recordings
        WHEN NEW.recording_identity IS NULL OR trim(NEW.recording_identity) = ''
        BEGIN
            UPDATE recordings
            SET recording_identity =
                lower(hex(randomblob(4))) || '-' ||
                lower(hex(randomblob(2))) || '-4' ||
                substr(lower(hex(randomblob(2))), 2) || '-' ||
                substr('89ab', ((random() & 3) + 1), 1) ||
                substr(lower(hex(randomblob(2))), 2) || '-' ||
                lower(hex(randomblob(6)))
            WHERE id = NEW.id;
        END
        """,
        """
        CREATE TRIGGER recordings_identity_immutable
        BEFORE UPDATE OF recording_identity ON recordings
        WHEN OLD.recording_identity IS NOT NULL
         AND NEW.recording_identity IS NOT OLD.recording_identity
        BEGIN
            SELECT RAISE(ABORT, 'recording identity is immutable');
        END
        """,
        """
        CREATE TRIGGER stations_uuid_immutable
        BEFORE UPDATE OF station_uuid ON stations
        WHEN OLD.station_uuid IS NOT NULL
         AND trim(OLD.station_uuid) != ''
         AND NEW.station_uuid IS NOT OLD.station_uuid
        BEGIN
            SELECT RAISE(ABORT, 'station UUID is immutable');
        END
        """,
    )
    for statement in trigger_statements:
        connection.execute(statement)

    checksum_count = int(
        connection.execute(
            "SELECT COUNT(*) FROM recordings WHERE content_sha256 IS NOT NULL"
        ).fetchone()[0]
    )
    null_checksum_count = len(rows) - checksum_count
    elapsed_ms = (time.perf_counter() - started) * 1000
    connection.execute(
        """
        INSERT INTO station_sync_migration_runs (
            migration_version, station_uuids_assigned,
            recording_identities_assigned, historical_checksums_populated,
            historical_checksums_left_null, elapsed_ms, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            migration_version,
            station_uuids_assigned,
            recording_identities_assigned,
            0,
            null_checksum_count,
            elapsed_ms,
            utc_now_iso(),
        ),
    )
    return {
        "station_uuids_assigned": station_uuids_assigned,
        "recording_identities_assigned": recording_identities_assigned,
        "historical_checksums_populated": 0,
        "historical_checksums_left_null": null_checksum_count,
        "elapsed_ms": elapsed_ms,
    }
