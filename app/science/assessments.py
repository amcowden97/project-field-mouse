"""Explicit, append-only Assessment provenance operations."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Iterable

from app.science import ScienceInvariantError


class AssessmentResult(StrEnum):
    SUPPORTED = "SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    ALTERNATE_TAXON = "ALTERNATE_TAXON"


@dataclass(frozen=True)
class AssessmentRecord:
    assessment_id: int
    assessment_identity: str
    payload_schema_version: int
    detection_id: int
    result: str
    assessed_scientific_name: str | None
    assessed_common_name: str
    alternate_scientific_name: str | None
    alternate_common_name: str | None
    reason_code: str
    reasoning: str
    created_by: str
    supersedes_assessment_id: int | None
    input_fingerprint: str
    idempotency_key: str
    created_at: str


@dataclass(frozen=True)
class AssessmentEvidenceRecord:
    assessment_evidence_id: int
    assessment_id: int
    evidence_id: int
    created_at: str


ASSESSMENT_COLUMNS = """
assessment_id, assessment_identity, payload_schema_version, detection_id, result,
assessed_scientific_name, assessed_common_name, alternate_scientific_name,
alternate_common_name, reason_code, reasoning, created_by,
supersedes_assessment_id, input_fingerprint, idempotency_key, created_at
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assessment_record(row: tuple | sqlite3.Row) -> AssessmentRecord:
    return AssessmentRecord(*row)


def _fingerprint(
    *,
    detection_id: int,
    result: AssessmentResult,
    evidence_ids: tuple[int, ...],
    assessed_scientific_name: str | None,
    assessed_common_name: str,
    alternate_scientific_name: str | None,
    alternate_common_name: str | None,
    reason_code: str,
    reasoning: str,
    created_by: str,
    supersedes_assessment_id: int | None,
) -> str:
    payload = {
        "alternate_common_name": alternate_common_name,
        "alternate_scientific_name": alternate_scientific_name,
        "assessed_common_name": assessed_common_name,
        "assessed_scientific_name": assessed_scientific_name,
        "created_by": created_by,
        "detection_id": detection_id,
        "evidence_ids": evidence_ids,
        "reason_code": reason_code,
        "reasoning": reasoning,
        "result": result.value,
        "supersedes_assessment_id": supersedes_assessment_id,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def create_assessment(
    connection: sqlite3.Connection,
    *,
    detection_id: int,
    result: AssessmentResult | str,
    evidence_ids: Iterable[int],
    reason_code: str,
    reasoning: str,
    created_by: str,
    idempotency_key: str,
    alternate_scientific_name: str | None = None,
    alternate_common_name: str | None = None,
    supersedes_assessment_id: int | None = None,
    assessment_identity: str | None = None,
    created_at: str | None = None,
) -> int:
    """Atomically append an explicit Assessment and exact Evidence set."""
    required = (reason_code, reasoning, created_by, idempotency_key)
    if any(not value or not value.strip() for value in required):
        raise ScienceInvariantError("Assessment provenance and reasoning are required")
    try:
        normalized_result = AssessmentResult(result)
    except (TypeError, ValueError) as error:
        raise ScienceInvariantError(f"Unknown Assessment result: {result}") from error
    normalized_idempotency_key = idempotency_key.strip()
    detection = connection.execute(
        "SELECT scientific_name, common_name FROM detections WHERE id = ?",
        (detection_id,),
    ).fetchone()
    if detection is None:
        raise ScienceInvariantError(f"Unknown Detection: {detection_id}")
    if normalized_result is AssessmentResult.ALTERNATE_TAXON:
        if not (
            str(alternate_scientific_name or "").strip()
            or str(alternate_common_name or "").strip()
        ):
            raise ScienceInvariantError("ALTERNATE_TAXON requires an alternate taxon")
    elif alternate_scientific_name is not None or alternate_common_name is not None:
        raise ScienceInvariantError("Only ALTERNATE_TAXON may supply an alternate taxon")

    supplied_evidence = tuple(evidence_ids)
    if not supplied_evidence:
        raise ScienceInvariantError("Assessment requires at least one Evidence item")
    if len(set(supplied_evidence)) != len(supplied_evidence):
        raise ScienceInvariantError("Duplicate AssessmentEvidence")
    ordered_evidence = tuple(sorted(supplied_evidence))
    for evidence_id in ordered_evidence:
        evidence = connection.execute(
            "SELECT detection_id FROM evidence WHERE evidence_id = ?",
            (evidence_id,),
        ).fetchone()
        if evidence is None:
            raise ScienceInvariantError(f"Unknown Evidence: {evidence_id}")
        if int(evidence[0]) != detection_id:
            raise ScienceInvariantError(
                "AssessmentEvidence must target the assessed Detection"
            )

    if supersedes_assessment_id is not None:
        prior = connection.execute(
            "SELECT detection_id FROM assessments WHERE assessment_id = ?",
            (supersedes_assessment_id,),
        ).fetchone()
        if prior is None:
            raise ScienceInvariantError(
                f"Unknown superseded Assessment: {supersedes_assessment_id}"
            )
        if int(prior[0]) != detection_id:
            raise ScienceInvariantError(
                "Assessment supersession must remain within one Detection"
            )

    assessed_scientific_name = detection[0]
    assessed_common_name = str(detection[1])
    fingerprint = _fingerprint(
        detection_id=detection_id,
        result=normalized_result,
        evidence_ids=ordered_evidence,
        assessed_scientific_name=assessed_scientific_name,
        assessed_common_name=assessed_common_name,
        alternate_scientific_name=alternate_scientific_name,
        alternate_common_name=alternate_common_name,
        reason_code=reason_code.strip(),
        reasoning=reasoning.strip(),
        created_by=created_by.strip(),
        supersedes_assessment_id=supersedes_assessment_id,
    )
    existing = connection.execute(
        "SELECT assessment_id, input_fingerprint FROM assessments WHERE idempotency_key = ?",
        (normalized_idempotency_key,),
    ).fetchone()
    if existing is not None:
        if str(existing[1]) != fingerprint:
            raise ScienceInvariantError(
                "Assessment idempotency key was reused with different inputs"
            )
        return int(existing[0])

    timestamp = created_at or _now()
    identity = assessment_identity or f"assessment:{uuid.uuid4()}"
    connection.execute("SAVEPOINT create_scientific_assessment")
    try:
        cursor = connection.execute(
            """
            INSERT INTO assessments (
                assessment_identity, detection_id, result,
                assessed_scientific_name, assessed_common_name,
                alternate_scientific_name, alternate_common_name,
                reason_code, reasoning, created_by, supersedes_assessment_id,
                input_fingerprint, idempotency_key, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identity,
                detection_id,
                normalized_result.value,
                assessed_scientific_name,
                assessed_common_name,
                alternate_scientific_name,
                alternate_common_name,
                reason_code.strip(),
                reasoning.strip(),
                created_by.strip(),
                supersedes_assessment_id,
                fingerprint,
                normalized_idempotency_key,
                timestamp,
            ),
        )
        if cursor.lastrowid is None:
            raise ScienceInvariantError("Assessment did not return an ID")
        assessment_id = int(cursor.lastrowid)
        for evidence_id in ordered_evidence:
            connection.execute(
                """
                INSERT INTO assessment_evidence (
                    assessment_id, evidence_id, created_at
                ) VALUES (?, ?, ?)
                """,
                (assessment_id, evidence_id, timestamp),
            )
        connection.execute("RELEASE SAVEPOINT create_scientific_assessment")
        return assessment_id
    except (sqlite3.Error, ScienceInvariantError) as error:
        connection.execute("ROLLBACK TO SAVEPOINT create_scientific_assessment")
        connection.execute("RELEASE SAVEPOINT create_scientific_assessment")
        if isinstance(error, ScienceInvariantError):
            raise
        raise ScienceInvariantError(str(error)) from error


def get_assessment(
    connection: sqlite3.Connection,
    assessment_id: int,
) -> AssessmentRecord | None:
    row = connection.execute(
        f"SELECT {ASSESSMENT_COLUMNS} FROM assessments WHERE assessment_id = ?",
        (assessment_id,),
    ).fetchone()
    return _assessment_record(row) if row is not None else None


def list_assessment_history(
    connection: sqlite3.Connection,
    detection_id: int,
) -> list[AssessmentRecord]:
    rows = connection.execute(
        f"""
        SELECT {ASSESSMENT_COLUMNS}
        FROM assessments
        WHERE detection_id = ?
        ORDER BY created_at, assessment_id
        """,
        (detection_id,),
    ).fetchall()
    return [_assessment_record(row) for row in rows]


def list_current_assessments(
    connection: sqlite3.Connection,
    detection_id: int,
) -> list[AssessmentRecord]:
    """Return every non-superseded Assessment without inventing consensus."""
    columns = ", ".join(
        f"assessment.{column.strip()}" for column in ASSESSMENT_COLUMNS.split(",")
    )
    rows = connection.execute(
        f"""
        SELECT {columns}
        FROM assessments AS assessment
        WHERE assessment.detection_id = ?
          AND NOT EXISTS (
              SELECT 1 FROM assessments AS replacement
              WHERE replacement.supersedes_assessment_id = assessment.assessment_id
          )
        ORDER BY assessment.created_at, assessment.assessment_id
        """,
        (detection_id,),
    ).fetchall()
    return [_assessment_record(row) for row in rows]


def get_assessment_evidence(
    connection: sqlite3.Connection,
    assessment_id: int,
) -> list[AssessmentEvidenceRecord]:
    rows = connection.execute(
        """
        SELECT assessment_evidence_id, assessment_id, evidence_id, created_at
        FROM assessment_evidence
        WHERE assessment_id = ?
        ORDER BY assessment_evidence_id
        """,
        (assessment_id,),
    ).fetchall()
    return [AssessmentEvidenceRecord(*row) for row in rows]
