"""Explicit, candidate-only Ground Truth dataset membership operations."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from app.science import ScienceInvariantError


class GroundTruthStage(StrEnum):
    CANDIDATE_POOL = "CANDIDATE_POOL"


@dataclass(frozen=True)
class GroundTruthDatasetRecord:
    dataset_id: int
    dataset_identity: str
    name: str
    purpose: str
    nomination_policy_version: str
    created_by: str
    created_at: str


@dataclass(frozen=True)
class GroundTruthMemberRecord:
    ground_truth_member_id: int
    member_identity: str
    dataset_id: int
    assessment_id: int
    stage: str
    nomination_reason_code: str
    nomination_reasoning: str
    nominated_by: str
    nomination_policy_version: str
    supersedes_member_id: int | None
    input_fingerprint: str
    idempotency_key: str
    created_at: str


DATASET_COLUMNS = """
dataset_id, dataset_identity, name, purpose, nomination_policy_version,
created_by, created_at
"""

MEMBER_COLUMNS = """
ground_truth_member_id, member_identity, dataset_id, assessment_id, stage,
nomination_reason_code, nomination_reasoning, nominated_by,
nomination_policy_version, supersedes_member_id, input_fingerprint,
idempotency_key, created_at
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required(values: tuple[str, ...], message: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values)
    if any(not value for value in normalized):
        raise ScienceInvariantError(message)
    return normalized


def create_ground_truth_dataset(
    connection: sqlite3.Connection,
    *,
    dataset_identity: str,
    name: str,
    purpose: str,
    nomination_policy_version: str,
    created_by: str,
    created_at: str | None = None,
) -> int:
    """Create an immutable named candidate dataset, idempotent by identity."""
    identity, normalized_name, normalized_purpose, policy, actor = _required(
        (dataset_identity, name, purpose, nomination_policy_version, created_by),
        "Ground Truth dataset identity and creation provenance are required",
    )
    existing = connection.execute(
        f"SELECT {DATASET_COLUMNS} FROM ground_truth_datasets " "WHERE dataset_identity = ?",
        (identity,),
    ).fetchone()
    if existing is not None:
        stored = GroundTruthDatasetRecord(*existing)
        if (
            stored.name != normalized_name
            or stored.purpose != normalized_purpose
            or stored.nomination_policy_version != policy
            or stored.created_by != actor
        ):
            raise ScienceInvariantError(
                "Ground Truth dataset identity was reused with different inputs"
            )
        return stored.dataset_id
    try:
        cursor = connection.execute(
            """
            INSERT INTO ground_truth_datasets (
                dataset_identity, name, purpose, nomination_policy_version,
                created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (identity, normalized_name, normalized_purpose, policy, actor, created_at or _now()),
        )
    except sqlite3.Error as error:
        raise ScienceInvariantError(str(error)) from error
    if cursor.lastrowid is None:
        raise ScienceInvariantError("Ground Truth dataset did not return an ID")
    return int(cursor.lastrowid)


def get_ground_truth_dataset(
    connection: sqlite3.Connection,
    dataset_id: int,
) -> GroundTruthDatasetRecord | None:
    row = connection.execute(
        f"SELECT {DATASET_COLUMNS} FROM ground_truth_datasets WHERE dataset_id = ?",
        (dataset_id,),
    ).fetchone()
    return GroundTruthDatasetRecord(*row) if row is not None else None


def _fingerprint(
    *,
    dataset_id: int,
    assessment_id: int,
    reason_code: str,
    reasoning: str,
    nominated_by: str,
    policy_version: str,
    supersedes_member_id: int | None,
    member_identity: str | None,
) -> str:
    payload = {
        "assessment_id": assessment_id,
        "dataset_id": dataset_id,
        "nominated_by": nominated_by,
        "nomination_policy_version": policy_version,
        "nomination_reason_code": reason_code,
        "nomination_reasoning": reasoning,
        "stage": GroundTruthStage.CANDIDATE_POOL.value,
        "supersedes_member_id": supersedes_member_id,
        "member_identity": member_identity,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_bounded_provenance(
    connection: sqlite3.Connection,
    assessment_id: int,
) -> None:
    assessment = connection.execute(
        """
        SELECT assessment.detection_id, detection.recording_id,
               detection.start_time, detection.end_time
        FROM assessments AS assessment
        JOIN detections AS detection ON detection.id = assessment.detection_id
        WHERE assessment.assessment_id = ?
        """,
        (assessment_id,),
    ).fetchone()
    if assessment is None:
        raise ScienceInvariantError(f"Unknown Assessment: {assessment_id}")
    start, end = assessment[2], assessment[3]
    if (
        start is None
        or end is None
        or not math.isfinite(float(start))
        or not math.isfinite(float(end))
        or float(start) < 0
        or float(end) <= float(start)
    ):
        raise ScienceInvariantError("Ground Truth candidate requires bounded Detection offsets")
    source = connection.execute(
        """
        SELECT recording.source_availability
        FROM assessment_evidence AS cited
        JOIN evidence_sources AS source ON source.evidence_id = cited.evidence_id
        JOIN recordings AS recording ON recording.id = source.recording_id
        WHERE cited.assessment_id = ?
          AND source.recording_id = ?
          AND source.interval_start_seconds IS NOT NULL
          AND source.interval_end_seconds IS NOT NULL
          AND source.interval_start_seconds <= ?
          AND source.interval_end_seconds >= ?
          AND recording.source_availability = 'AVAILABLE'
        LIMIT 1
        """,
        (assessment_id, int(assessment[1]), float(start), float(end)),
    ).fetchone()
    if source is not None:
        return
    bounded_source = connection.execute(
        """
        SELECT 1
        FROM assessment_evidence AS cited
        JOIN evidence_sources AS source ON source.evidence_id = cited.evidence_id
        WHERE cited.assessment_id = ?
          AND source.recording_id = ?
          AND source.interval_start_seconds IS NOT NULL
          AND source.interval_end_seconds IS NOT NULL
          AND source.interval_start_seconds <= ?
          AND source.interval_end_seconds >= ?
        LIMIT 1
        """,
        (assessment_id, int(assessment[1]), float(start), float(end)),
    ).fetchone()
    if bounded_source is not None:
        raise ScienceInvariantError("Ground Truth candidate source must be AVAILABLE at nomination")
    raise ScienceInvariantError(
        "Ground Truth candidate requires Assessment-cited bounded source provenance"
    )


def nominate_ground_truth_candidate(
    connection: sqlite3.Connection,
    *,
    dataset_id: int,
    assessment_id: int,
    nomination_reason_code: str,
    nomination_reasoning: str,
    nominated_by: str,
    nomination_policy_version: str,
    idempotency_key: str,
    supersedes_member_id: int | None = None,
    member_identity: str | None = None,
    created_at: str | None = None,
) -> int:
    """Atomically nominate one exact Assessment-backed bounded event."""
    reason_code, reasoning, actor, policy, retry_key = _required(
        (
            nomination_reason_code,
            nomination_reasoning,
            nominated_by,
            nomination_policy_version,
            idempotency_key,
        ),
        "Ground Truth nomination provenance and idempotency key are required",
    )
    dataset = get_ground_truth_dataset(connection, dataset_id)
    if dataset is None:
        raise ScienceInvariantError(f"Unknown Ground Truth dataset: {dataset_id}")
    if dataset.nomination_policy_version != policy:
        raise ScienceInvariantError("Nomination policy version must match the Ground Truth dataset")
    supplied_identity = member_identity.strip() if member_identity is not None else None
    if supplied_identity == "":
        raise ScienceInvariantError("Ground Truth member identity is required")
    fingerprint = _fingerprint(
        dataset_id=dataset_id,
        assessment_id=assessment_id,
        reason_code=reason_code,
        reasoning=reasoning,
        nominated_by=actor,
        policy_version=policy,
        supersedes_member_id=supersedes_member_id,
        member_identity=supplied_identity,
    )
    existing = connection.execute(
        """
        SELECT ground_truth_member_id, input_fingerprint
        FROM ground_truth_members WHERE idempotency_key = ?
        """,
        (retry_key,),
    ).fetchone()
    if existing is not None:
        if str(existing[1]) != fingerprint:
            raise ScienceInvariantError(
                "Ground Truth idempotency key was reused with different inputs"
            )
        return int(existing[0])

    _validate_bounded_provenance(connection, assessment_id)
    if supersedes_member_id is not None:
        prior = connection.execute(
            """
            SELECT dataset_id FROM ground_truth_members
            WHERE ground_truth_member_id = ?
            """,
            (supersedes_member_id,),
        ).fetchone()
        if prior is None:
            raise ScienceInvariantError(
                f"Unknown superseded Ground Truth member: {supersedes_member_id}"
            )
        if int(prior[0]) != dataset_id:
            raise ScienceInvariantError("Ground Truth supersession must remain within one dataset")

    identity = supplied_identity or f"ground-truth-member:{uuid.uuid4()}"
    connection.execute("SAVEPOINT nominate_ground_truth_candidate")
    try:
        cursor = connection.execute(
            """
            INSERT INTO ground_truth_members (
                member_identity, dataset_id, assessment_id, stage,
                nomination_reason_code, nomination_reasoning, nominated_by,
                nomination_policy_version, supersedes_member_id,
                input_fingerprint, idempotency_key, created_at
            ) VALUES (?, ?, ?, 'CANDIDATE_POOL', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identity,
                dataset_id,
                assessment_id,
                reason_code,
                reasoning,
                actor,
                policy,
                supersedes_member_id,
                fingerprint,
                retry_key,
                created_at or _now(),
            ),
        )
        if cursor.lastrowid is None:
            raise ScienceInvariantError("Ground Truth nomination did not return an ID")
        member_id = int(cursor.lastrowid)
        connection.execute("RELEASE SAVEPOINT nominate_ground_truth_candidate")
        return member_id
    except (sqlite3.Error, ScienceInvariantError) as error:
        connection.execute("ROLLBACK TO SAVEPOINT nominate_ground_truth_candidate")
        connection.execute("RELEASE SAVEPOINT nominate_ground_truth_candidate")
        if isinstance(error, ScienceInvariantError):
            raise
        raise ScienceInvariantError(str(error)) from error


def get_ground_truth_member(
    connection: sqlite3.Connection,
    ground_truth_member_id: int,
) -> GroundTruthMemberRecord | None:
    row = connection.execute(
        f"SELECT {MEMBER_COLUMNS} FROM ground_truth_members " "WHERE ground_truth_member_id = ?",
        (ground_truth_member_id,),
    ).fetchone()
    return GroundTruthMemberRecord(*row) if row is not None else None


def list_ground_truth_member_history(
    connection: sqlite3.Connection,
    dataset_id: int,
) -> list[GroundTruthMemberRecord]:
    rows = connection.execute(
        f"""
        SELECT {MEMBER_COLUMNS} FROM ground_truth_members
        WHERE dataset_id = ? ORDER BY created_at, ground_truth_member_id
        """,
        (dataset_id,),
    ).fetchall()
    return [GroundTruthMemberRecord(*row) for row in rows]


def list_current_ground_truth_members(
    connection: sqlite3.Connection,
    dataset_id: int,
) -> list[GroundTruthMemberRecord]:
    columns = ", ".join(f"member.{column.strip()}" for column in MEMBER_COLUMNS.split(","))
    rows = connection.execute(
        f"""
        SELECT {columns}
        FROM ground_truth_members AS member
        WHERE member.dataset_id = ?
          AND NOT EXISTS (
              SELECT 1 FROM ground_truth_members AS replacement
              WHERE replacement.supersedes_member_id =
                    member.ground_truth_member_id
          )
        ORDER BY member.created_at, member.ground_truth_member_id
        """,
        (dataset_id,),
    ).fetchall()
    return [GroundTruthMemberRecord(*row) for row in rows]
