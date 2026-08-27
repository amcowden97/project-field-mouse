"""Recording identity and media lifecycle operations."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from enum import StrEnum

from app.science import ScienceInvariantError


class SourceAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    INTENTIONALLY_EXPIRED = "INTENTIONALLY_EXPIRED"
    MISSING = "MISSING"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_availability(
    connection: sqlite3.Connection,
    recording_id: int,
) -> SourceAvailability:
    row = connection.execute(
        "SELECT source_availability FROM recordings WHERE id = ?",
        (recording_id,),
    ).fetchone()
    if row is None:
        raise ScienceInvariantError(f"Unknown recording: {recording_id}")
    return SourceAvailability(row[0])


def is_recording_protected(connection: sqlite3.Connection, recording_id: int) -> bool:
    return bool(
        connection.execute(
            """
            SELECT 1 FROM recording_protections
            WHERE recording_id = ? AND released_at IS NULL
            LIMIT 1
            """,
            (recording_id,),
        ).fetchone()
    )


def set_source_availability(
    connection: sqlite3.Connection,
    *,
    recording_id: int,
    availability: SourceAvailability,
    reason_code: str,
    authorized_by: str,
    authorization_reference: str,
    operation_id: str,
    occurred_at: str | None = None,
    metadata: dict | None = None,
) -> int:
    """Append provenance and update current availability in one transaction."""
    values = (reason_code, authorized_by, authorization_reference, operation_id)
    if any(not value or not value.strip() for value in values):
        raise ScienceInvariantError("Availability changes require complete provenance")
    current = source_availability(connection, recording_id)
    if (
        availability is SourceAvailability.INTENTIONALLY_EXPIRED
        and is_recording_protected(connection, recording_id)
    ):
        raise ScienceInvariantError("Active recording protection blocks expiration")
    timestamp = occurred_at or _now()
    payload = json.dumps(metadata or {}, sort_keys=True, separators=(",", ":"))
    connection.execute("SAVEPOINT recording_source_availability")
    try:
        cursor = connection.execute(
            """
            INSERT INTO recording_source_events (
                recording_id, from_availability, to_availability, reason_code,
                authorized_by, authorization_reference, operation_id,
                occurred_at, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recording_id,
                current.value,
                availability.value,
                reason_code,
                authorized_by,
                authorization_reference,
                operation_id,
                timestamp,
                _now(),
                payload,
            ),
        )
        connection.execute(
            """
            UPDATE recordings
            SET source_availability = ?, source_last_verified_at = ?
            WHERE id = ?
            """,
            (availability.value, timestamp, recording_id),
        )
        if cursor.lastrowid is None:
            raise ScienceInvariantError("Source lifecycle event did not return an ID")
        event_id = int(cursor.lastrowid)
        connection.execute("RELEASE SAVEPOINT recording_source_availability")
    except (sqlite3.Error, ScienceInvariantError) as error:
        connection.execute("ROLLBACK TO SAVEPOINT recording_source_availability")
        connection.execute("RELEASE SAVEPOINT recording_source_availability")
        if isinstance(error, ScienceInvariantError):
            raise
        raise ScienceInvariantError(str(error)) from error
    return event_id
