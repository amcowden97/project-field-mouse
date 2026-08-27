"""Conservative RC1.1-to-RC1.2 recording lifecycle backfill."""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_exists(raw_path: str) -> bool:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.is_file()


def _event(
    connection: sqlite3.Connection,
    *,
    recording_id: int,
    from_availability: str | None,
    to_availability: str,
    reason_code: str,
    authorization_reference: str,
    operation_id: str,
    occurred_at: str,
) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO recording_source_events (
            recording_id, from_availability, to_availability, reason_code,
            authorized_by, authorization_reference, operation_id,
            occurred_at, created_at, metadata_json
        ) VALUES (?, ?, ?, ?, 'SCHEMA_MIGRATION', ?, ?, ?, ?, '{}')
        """,
        (
            recording_id,
            from_availability,
            to_availability,
            reason_code,
            authorization_reference,
            operation_id,
            occurred_at,
            occurred_at,
        ),
    )


def backfill_recording_lifecycle(
    connection: sqlite3.Connection,
    *,
    migration_version: int,
    index_creation_ms: float,
) -> dict[str, int | float | list[str]]:
    """Backfill availability without equating a missing path with expiration."""
    started_at = _now()
    started = time.perf_counter()
    rows = connection.execute(
        """
        SELECT id, station_id, file_path, processing_status, recording_identity
        FROM recordings ORDER BY id
        """
    ).fetchall()
    confident_expirations = 0
    ambiguous_absent = 0
    relative_missing = 0

    for row in rows:
        recording_id = int(row[0])
        station_id = str(row[1])
        raw_path = str(row[2])
        status = str(row[3]).casefold()
        occurred_at = _now()
        identity = row[4] or f"{station_id}:{recording_id:020d}"
        connection.execute(
            """
            UPDATE recordings
            SET recording_identity = ?, source_last_verified_at = ?
            WHERE id = ?
            """,
            (identity, occurred_at, recording_id),
        )
        present = _source_exists(raw_path)
        base_operation = f"migration-{migration_version}-recording-{recording_id}"

        if status == "audio_expired":
            confident_expirations += 1
            _event(
                connection,
                recording_id=recording_id,
                from_availability="MISSING",
                to_availability="INTENTIONALLY_EXPIRED",
                reason_code="RC1_1_AUDIO_EXPIRED_STATUS",
                authorization_reference="RC1.1 processing_status=audio_expired",
                operation_id=f"{base_operation}-expired",
                occurred_at=occurred_at,
            )
            connection.execute(
                "UPDATE recordings SET source_availability = 'INTENTIONALLY_EXPIRED' WHERE id = ?",
                (recording_id,),
            )
            if present:
                _event(
                    connection,
                    recording_id=recording_id,
                    from_availability="INTENTIONALLY_EXPIRED",
                    to_availability="AVAILABLE",
                    reason_code="SOURCE_PRESENT_DURING_MIGRATION",
                    authorization_reference=raw_path,
                    operation_id=f"{base_operation}-restored",
                    occurred_at=occurred_at,
                )
                connection.execute(
                    "UPDATE recordings SET source_availability = 'AVAILABLE' WHERE id = ?",
                    (recording_id,),
                )
        elif present:
            _event(
                connection,
                recording_id=recording_id,
                from_availability="MISSING",
                to_availability="AVAILABLE",
                reason_code="SOURCE_PRESENT_DURING_MIGRATION",
                authorization_reference=raw_path,
                operation_id=f"{base_operation}-available",
                occurred_at=occurred_at,
            )
            connection.execute(
                "UPDATE recordings SET source_availability = 'AVAILABLE' WHERE id = ?",
                (recording_id,),
            )
        else:
            ambiguous_absent += 1
            if not Path(raw_path).is_absolute():
                relative_missing += 1
            _event(
                connection,
                recording_id=recording_id,
                from_availability="MISSING",
                to_availability="MISSING",
                reason_code="SOURCE_NOT_FOUND_DURING_MIGRATION",
                authorization_reference=raw_path,
                operation_id=f"{base_operation}-missing",
                occurred_at=occurred_at,
            )

    counts = {
        str(row[0]): int(row[1])
        for row in connection.execute(
            "SELECT source_availability, COUNT(*) FROM recordings GROUP BY source_availability"
        ).fetchall()
    }
    elapsed_ms = (time.perf_counter() - started) * 1000
    warnings = []
    if ambiguous_absent:
        warnings.append(
            f"{ambiguous_absent} absent source(s) lacked affirmative expiration provenance"
        )
    if relative_missing:
        warnings.append(f"{relative_missing} missing source path(s) were relative")
    completed_at = _now()
    connection.execute(
        """
        INSERT INTO evidence_schema_migration_runs (
            migration_version, started_at, completed_at, total_recordings,
            available_count, intentionally_expired_count, missing_count,
            confident_expiration_count, ambiguous_absent_count,
            availability_backfill_ms, index_creation_ms, warnings_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            migration_version,
            started_at,
            completed_at,
            len(rows),
            counts.get("AVAILABLE", 0),
            counts.get("INTENTIONALLY_EXPIRED", 0),
            counts.get("MISSING", 0),
            confident_expirations,
            ambiguous_absent,
            elapsed_ms,
            index_creation_ms,
            json.dumps(warnings, separators=(",", ":")),
        ),
    )
    return {
        "total_recordings": len(rows),
        "available": counts.get("AVAILABLE", 0),
        "intentionally_expired": counts.get("INTENTIONALLY_EXPIRED", 0),
        "missing": counts.get("MISSING", 0),
        "confident_expirations": confident_expirations,
        "ambiguous_absent": ambiguous_absent,
        "availability_backfill_ms": elapsed_ms,
        "index_creation_ms": index_creation_ms,
        "warnings": warnings,
    }

