"""Multi-valued recording protection history."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from enum import StrEnum

from app.science import ScienceInvariantError


class ProtectionType(StrEnum):
    MANUALLY_PINNED = "MANUALLY_PINNED"
    FIRST_CONFIRMED = "FIRST_CONFIRMED"
    VERIFICATION_EVIDENCE = "VERIFICATION_EVIDENCE"
    GROUND_TRUTH_EVIDENCE = "GROUND_TRUTH_EVIDENCE"
    SCIENTIFICALLY_INTERESTING = "SCIENTIFICALLY_INTERESTING"
    RESEARCH_HOLD = "RESEARCH_HOLD"
    SIGNIFICANT_OBSERVATION = "SIGNIFICANT_OBSERVATION"


class ProtectionOrigin(StrEnum):
    MANUAL = "MANUAL"
    EVIDENCE = "EVIDENCE"
    REVIEW = "REVIEW"
    OBSERVATION = "OBSERVATION"
    GROUND_TRUTH = "GROUND_TRUTH"
    RESEARCH = "RESEARCH"
    SYSTEM_POLICY = "SYSTEM_POLICY"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_recording_protection(
    connection: sqlite3.Connection,
    *,
    recording_id: int,
    protection_type: ProtectionType,
    origin_type: ProtectionOrigin,
    origin_reference: str,
    reason_code: str,
    reason: str,
    created_by: str,
    origin_evidence_id: int | None = None,
    created_at: str | None = None,
) -> int:
    if origin_type is ProtectionOrigin.EVIDENCE and origin_evidence_id is None:
        raise ScienceInvariantError("EVIDENCE protection origin requires an Evidence ID")
    if origin_type is not ProtectionOrigin.EVIDENCE and origin_evidence_id is not None:
        raise ScienceInvariantError("Only EVIDENCE origins may reference Evidence")
    values = (origin_reference, reason_code, reason, created_by)
    if any(not value or not value.strip() for value in values):
        raise ScienceInvariantError("Recording protection provenance is incomplete")
    try:
        cursor = connection.execute(
            """
            INSERT INTO recording_protections (
                recording_id, protection_type, origin_type, origin_reference,
                origin_evidence_id, reason_code, reason, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recording_id,
                protection_type.value,
                origin_type.value,
                origin_reference,
                origin_evidence_id,
                reason_code,
                reason,
                created_by,
                created_at or _now(),
            ),
        )
    except sqlite3.IntegrityError as error:
        raise ScienceInvariantError(str(error)) from error
    if cursor.lastrowid is None:
        raise ScienceInvariantError("Recording protection did not return an ID")
    return int(cursor.lastrowid)


def release_recording_protection(
    connection: sqlite3.Connection,
    *,
    protection_id: int,
    released_by: str,
    release_reason: str,
    released_at: str | None = None,
) -> None:
    if not released_by.strip() or not release_reason.strip():
        raise ScienceInvariantError("Protection release requires actor and reason")
    try:
        cursor = connection.execute(
            """
            UPDATE recording_protections
            SET released_at = ?, released_by = ?, release_reason = ?
            WHERE protection_id = ? AND released_at IS NULL
            """,
            (released_at or _now(), released_by, release_reason, protection_id),
        )
    except sqlite3.IntegrityError as error:
        raise ScienceInvariantError(str(error)) from error
    if cursor.rowcount != 1:
        raise ScienceInvariantError("Protection is unknown or already released")

