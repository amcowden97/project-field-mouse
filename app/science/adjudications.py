"""Explicit, append-only Ground Truth adjudication provenance operations."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Iterable

from app.science import ScienceInvariantError
from app.science.protections import (
    ProtectionOrigin,
    ProtectionType,
    add_recording_protection,
)


class GroundTruthAdjudicationResult(StrEnum):
    CONFIRMED_TAXON = "CONFIRMED_TAXON"
    DETECTOR_CLAIM_NOT_SUPPORTED = "DETECTOR_CLAIM_NOT_SUPPORTED"
    ALTERNATE_TAXON = "ALTERNATE_TAXON"
    UNRESOLVED = "UNRESOLVED"


class GroundTruthAdjudicatorRole(StrEnum):
    SCIENTIFIC_OWNER = "SCIENTIFIC_OWNER"
    EXPERT = "EXPERT"


class GroundTruthAdjudicationEvidenceRole(StrEnum):
    PRIMARY = "PRIMARY"
    SUPPORTING = "SUPPORTING"
    CONTEXT = "CONTEXT"


class GroundTruthAdjudicationEligibilityReason(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    CANDIDATE_NOT_FOUND = "CANDIDATE_NOT_FOUND"
    NOT_CURRENT_CANDIDATE = "NOT_CURRENT_CANDIDATE"
    INVALID_EVENT_PROVENANCE = "INVALID_EVENT_PROVENANCE"
    INVALID_EVIDENCE_PROVENANCE = "INVALID_EVIDENCE_PROVENANCE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    NO_CANONICAL_HUMAN_EVIDENCE = "NO_CANONICAL_HUMAN_EVIDENCE"
    UNRESOLVED_REVIEW_CONFLICT = "UNRESOLVED_REVIEW_CONFLICT"
    ADJUDICATOR_IDENTITY_REQUIRED = "ADJUDICATOR_IDENTITY_REQUIRED"
    ADJUDICATOR_AUTHORITY_REQUIRED = "ADJUDICATOR_AUTHORITY_REQUIRED"
    POLICY_VERSION_REQUIRED = "POLICY_VERSION_REQUIRED"
    INVALID_RESULT = "INVALID_RESULT"


@dataclass(frozen=True)
class GroundTruthAdjudicationEvidenceInput:
    evidence_id: int
    role: GroundTruthAdjudicationEvidenceRole


@dataclass(frozen=True)
class GroundTruthAdjudicationEligibility:
    eligible: bool
    reasons: tuple[str, ...]
    ground_truth_member_id: int
    assessment_id: int | None
    detection_id: int | None
    required_recording_ids: tuple[int, ...]
    material_review_conflict: bool


@dataclass(frozen=True)
class GroundTruthAdjudicationRecord:
    ground_truth_adjudication_id: int
    adjudication_identity: str
    ground_truth_member_id: int
    result: str
    adjudicated_scientific_name: str | None
    adjudicated_common_name: str | None
    reason_code: str
    reasoning: str
    adjudicated_by: str
    adjudicator_role: str
    policy_version: str
    supersedes_adjudication_id: int | None
    input_fingerprint: str
    idempotency_key: str
    created_at: str


@dataclass(frozen=True)
class GroundTruthAdjudicationEvidenceRecord:
    ground_truth_adjudication_evidence_id: int
    ground_truth_adjudication_id: int
    evidence_id: int
    relationship_role: str
    created_at: str


ADJUDICATION_COLUMNS = """
ground_truth_adjudication_id, adjudication_identity, ground_truth_member_id, result,
adjudicated_scientific_name, adjudicated_common_name, reason_code, reasoning,
adjudicated_by, adjudicator_role, policy_version, supersedes_adjudication_id,
input_fingerprint, idempotency_key, created_at
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required(values: tuple[str, ...], message: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values)
    if any(not value for value in normalized):
        raise ScienceInvariantError(message)
    return normalized


def _normalize_result(
    result: GroundTruthAdjudicationResult | str,
) -> GroundTruthAdjudicationResult:
    try:
        return GroundTruthAdjudicationResult(result)
    except (TypeError, ValueError) as error:
        raise ScienceInvariantError(
            f"Unknown Ground Truth adjudication result: {result}"
        ) from error


def _normalize_role(
    role: GroundTruthAdjudicatorRole | str,
) -> GroundTruthAdjudicatorRole:
    try:
        return GroundTruthAdjudicatorRole(role)
    except (TypeError, ValueError) as error:
        raise ScienceInvariantError(
            f"Unauthorized Ground Truth adjudicator role: {role}"
        ) from error


def _normalize_evidence(
    evidence: Iterable[GroundTruthAdjudicationEvidenceInput],
) -> tuple[GroundTruthAdjudicationEvidenceInput, ...]:
    normalized: list[GroundTruthAdjudicationEvidenceInput] = []
    seen: set[int] = set()
    for item in evidence:
        try:
            role = GroundTruthAdjudicationEvidenceRole(item.role)
        except (TypeError, ValueError) as error:
            raise ScienceInvariantError(
                f"Unknown Ground Truth Evidence relationship role: {item.role}"
            ) from error
        if item.evidence_id in seen:
            raise ScienceInvariantError("Duplicate Ground Truth adjudication Evidence")
        seen.add(item.evidence_id)
        normalized.append(GroundTruthAdjudicationEvidenceInput(item.evidence_id, role))
    if not normalized:
        raise ScienceInvariantError("Ground Truth adjudication requires Evidence")
    return tuple(sorted(normalized, key=lambda item: (item.evidence_id, item.role.value)))


def _review_position(
    decision: str,
    proposed_scientific_name: str | None,
    proposed_common_name: str | None,
    detection_scientific_name: str | None,
    detection_common_name: str,
) -> tuple[str, str, str]:
    if decision == "CONFIRM":
        return (
            "TAXON",
            (detection_scientific_name or "").strip().casefold(),
            detection_common_name.strip().casefold(),
        )
    if decision == "CORRECT_TAXON":
        return (
            "TAXON",
            (proposed_scientific_name or "").strip().casefold(),
            (proposed_common_name or "").strip().casefold(),
        )
    if decision == "REJECT":
        return ("DETECTOR_CLAIM_NOT_SUPPORTED", "", "")
    return ("UNRESOLVED", "", "")


def _has_material_review_conflict(
    connection: sqlite3.Connection,
    detection_id: int,
    scientific_name: str | None,
    common_name: str,
) -> bool:
    rows = connection.execute(
        """
        SELECT review.decision, review.proposed_scientific_name,
               review.proposed_common_name
        FROM reviews AS review
        WHERE review.detection_id = ?
          AND review.reviewer_role IN ('USER', 'EXPERT')
          AND NOT EXISTS (
              SELECT 1 FROM reviews AS replacement
              WHERE replacement.supersedes_review_id = review.review_id
          )
        ORDER BY review.review_id
        """,
        (detection_id,),
    ).fetchall()
    positions = {
        _review_position(row[0], row[1], row[2], scientific_name, common_name) for row in rows
    }
    return len(positions) > 1


def evaluate_ground_truth_adjudication_eligibility(
    connection: sqlite3.Connection,
    *,
    ground_truth_member_id: int,
    evidence: Iterable[GroundTruthAdjudicationEvidenceInput],
    adjudicated_by: str,
    adjudicator_role: GroundTruthAdjudicatorRole | str,
    policy_version: str,
    result: GroundTruthAdjudicationResult | str,
) -> GroundTruthAdjudicationEligibility:
    """Evaluate current adjudication eligibility without creating durable state."""
    reasons: list[GroundTruthAdjudicationEligibilityReason] = []
    evidence_items = tuple(evidence)
    try:
        normalized_role = GroundTruthAdjudicatorRole(adjudicator_role)
    except (TypeError, ValueError):
        normalized_role = None
        reasons.append(GroundTruthAdjudicationEligibilityReason.ADJUDICATOR_AUTHORITY_REQUIRED)
    try:
        normalized_result = GroundTruthAdjudicationResult(result)
    except (TypeError, ValueError):
        normalized_result = None
        reasons.append(GroundTruthAdjudicationEligibilityReason.INVALID_RESULT)
    if not adjudicated_by.strip():
        reasons.append(GroundTruthAdjudicationEligibilityReason.ADJUDICATOR_IDENTITY_REQUIRED)
    if not policy_version.strip():
        reasons.append(GroundTruthAdjudicationEligibilityReason.POLICY_VERSION_REQUIRED)

    member = connection.execute(
        """
        SELECT assessment_id, stage
        FROM ground_truth_members
        WHERE ground_truth_member_id = ?
        """,
        (ground_truth_member_id,),
    ).fetchone()
    if member is None:
        reasons.append(GroundTruthAdjudicationEligibilityReason.CANDIDATE_NOT_FOUND)
        return GroundTruthAdjudicationEligibility(
            False,
            tuple(reason.value for reason in reasons),
            ground_truth_member_id,
            None,
            None,
            (),
            False,
        )
    assessment_id = int(member[0])
    if (
        member[1] != "CANDIDATE_POOL"
        or connection.execute(
            """
        SELECT 1 FROM ground_truth_members
        WHERE supersedes_member_id = ? LIMIT 1
        """,
            (ground_truth_member_id,),
        ).fetchone()
    ):
        reasons.append(GroundTruthAdjudicationEligibilityReason.NOT_CURRENT_CANDIDATE)

    context = connection.execute(
        """
        SELECT assessment.detection_id, detection.recording_id,
               detection.start_time, detection.end_time,
               detection.scientific_name, detection.common_name
        FROM assessments AS assessment
        JOIN detections AS detection ON detection.id = assessment.detection_id
        WHERE assessment.assessment_id = ?
        """,
        (assessment_id,),
    ).fetchone()
    if context is None:
        reasons.append(GroundTruthAdjudicationEligibilityReason.INVALID_EVENT_PROVENANCE)
        return GroundTruthAdjudicationEligibility(
            False,
            tuple(dict.fromkeys(reason.value for reason in reasons)),
            ground_truth_member_id,
            assessment_id,
            None,
            (),
            False,
        )

    detection_id = int(context[0])
    detection_recording_id = int(context[1])
    try:
        start = float(context[2])
        end = float(context[3])
    except (TypeError, ValueError):
        start, end = math.nan, math.nan
    bounded_detection = math.isfinite(start) and math.isfinite(end) and start >= 0 and end > start
    if not bounded_detection:
        reasons.append(GroundTruthAdjudicationEligibilityReason.INVALID_EVENT_PROVENANCE)

    seen: set[int] = set()
    has_human = False
    required_recordings: set[int] = set()
    detection_source_covered = False
    source_unavailable = False
    for item in evidence_items:
        if item.evidence_id in seen:
            reasons.append(GroundTruthAdjudicationEligibilityReason.INVALID_EVIDENCE_PROVENANCE)
            continue
        seen.add(item.evidence_id)
        try:
            relationship_role = GroundTruthAdjudicationEvidenceRole(item.role)
        except (TypeError, ValueError):
            reasons.append(GroundTruthAdjudicationEligibilityReason.INVALID_EVIDENCE_PROVENANCE)
            continue
        row = connection.execute(
            "SELECT detection_id, family FROM evidence WHERE evidence_id = ?",
            (item.evidence_id,),
        ).fetchone()
        if row is None or int(row[0]) != detection_id:
            reasons.append(GroundTruthAdjudicationEligibilityReason.INVALID_EVIDENCE_PROVENANCE)
            continue
        has_human = has_human or row[1] in {"HUMAN", "EXPERT"}
        if relationship_role is GroundTruthAdjudicationEvidenceRole.CONTEXT:
            continue
        sources = connection.execute(
            """
            SELECT source.recording_id, source.interval_start_seconds,
                   source.interval_end_seconds, recording.source_availability
            FROM evidence_sources AS source
            JOIN recordings AS recording ON recording.id = source.recording_id
            WHERE source.evidence_id = ?
            ORDER BY source.evidence_source_id
            """,
            (item.evidence_id,),
        ).fetchall()
        for source in sources:
            if source[1] is None or source[2] is None or not bounded_detection:
                continue
            source_start = float(source[1])
            source_end = float(source[2])
            if source_start > start or source_end < end:
                continue
            recording_id = int(source[0])
            required_recordings.add(recording_id)
            detection_source_covered = (
                detection_source_covered or recording_id == detection_recording_id
            )
            source_unavailable = source_unavailable or source[3] != "AVAILABLE"

    if not evidence_items:
        reasons.append(GroundTruthAdjudicationEligibilityReason.INVALID_EVIDENCE_PROVENANCE)
    if not has_human:
        reasons.append(GroundTruthAdjudicationEligibilityReason.NO_CANONICAL_HUMAN_EVIDENCE)
    if not detection_source_covered:
        reasons.append(GroundTruthAdjudicationEligibilityReason.INVALID_EVENT_PROVENANCE)
    if source_unavailable:
        reasons.append(GroundTruthAdjudicationEligibilityReason.SOURCE_UNAVAILABLE)

    material_conflict = _has_material_review_conflict(
        connection,
        detection_id,
        context[4],
        str(context[5]),
    )
    if (
        material_conflict
        and normalized_result
        in {
            GroundTruthAdjudicationResult.CONFIRMED_TAXON,
            GroundTruthAdjudicationResult.ALTERNATE_TAXON,
        }
        and normalized_role is not GroundTruthAdjudicatorRole.EXPERT
    ):
        reasons.extend(
            (
                GroundTruthAdjudicationEligibilityReason.UNRESOLVED_REVIEW_CONFLICT,
                GroundTruthAdjudicationEligibilityReason.ADJUDICATOR_AUTHORITY_REQUIRED,
            )
        )

    unique_reasons = tuple(dict.fromkeys(reason.value for reason in reasons))
    return GroundTruthAdjudicationEligibility(
        not unique_reasons,
        unique_reasons or (GroundTruthAdjudicationEligibilityReason.ELIGIBLE.value,),
        ground_truth_member_id,
        assessment_id,
        detection_id,
        tuple(sorted(required_recordings)),
        material_conflict,
    )


def _fingerprint(
    *,
    ground_truth_member_id: int,
    result: GroundTruthAdjudicationResult,
    scientific_name: str | None,
    common_name: str | None,
    reason_code: str,
    reasoning: str,
    adjudicated_by: str,
    adjudicator_role: GroundTruthAdjudicatorRole,
    policy_version: str,
    evidence: tuple[GroundTruthAdjudicationEvidenceInput, ...],
    supersedes_adjudication_id: int | None,
    adjudication_identity: str | None,
) -> str:
    payload = {
        "adjudicated_by": adjudicated_by,
        "adjudicated_common_name": common_name,
        "adjudicated_scientific_name": scientific_name,
        "adjudication_identity": adjudication_identity,
        "adjudicator_role": adjudicator_role.value,
        "evidence": tuple((item.evidence_id, item.role.value) for item in evidence),
        "ground_truth_member_id": ground_truth_member_id,
        "policy_version": policy_version,
        "reason_code": reason_code,
        "reasoning": reasoning,
        "result": result.value,
        "supersedes_adjudication_id": supersedes_adjudication_id,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def create_ground_truth_adjudication(
    connection: sqlite3.Connection,
    *,
    ground_truth_member_id: int,
    result: GroundTruthAdjudicationResult | str,
    evidence: Iterable[GroundTruthAdjudicationEvidenceInput],
    reason_code: str,
    reasoning: str,
    adjudicated_by: str,
    adjudicator_role: GroundTruthAdjudicatorRole | str,
    policy_version: str,
    idempotency_key: str,
    adjudicated_scientific_name: str | None = None,
    adjudicated_common_name: str | None = None,
    supersedes_adjudication_id: int | None = None,
    adjudication_identity: str | None = None,
    created_at: str | None = None,
) -> int:
    """Atomically append an explicit adjudication, Evidence links, and protections."""
    reason, rationale, actor, policy, retry_key = _required(
        (reason_code, reasoning, adjudicated_by, policy_version, idempotency_key),
        "Ground Truth adjudication provenance and idempotency key are required",
    )
    normalized_result = _normalize_result(result)
    normalized_role = _normalize_role(adjudicator_role)
    evidence_items = _normalize_evidence(evidence)
    supplied_identity = adjudication_identity.strip() if adjudication_identity is not None else None
    if supplied_identity == "":
        raise ScienceInvariantError("Ground Truth adjudication identity is required")

    if normalized_result in {
        GroundTruthAdjudicationResult.CONFIRMED_TAXON,
        GroundTruthAdjudicationResult.ALTERNATE_TAXON,
    }:
        scientific_name = (
            adjudicated_scientific_name.strip() if adjudicated_scientific_name is not None else None
        )
        common_name = (
            adjudicated_common_name.strip() if adjudicated_common_name is not None else None
        )
        scientific_name = scientific_name or None
        common_name = common_name or None
        if scientific_name is None and common_name is None:
            raise ScienceInvariantError(f"{normalized_result.value} requires an adjudicated taxon")
    else:
        if adjudicated_scientific_name is not None or adjudicated_common_name is not None:
            raise ScienceInvariantError(
                f"{normalized_result.value} requires a NULL adjudicated taxon"
            )
        scientific_name = None
        common_name = None

    fingerprint = _fingerprint(
        ground_truth_member_id=ground_truth_member_id,
        result=normalized_result,
        scientific_name=scientific_name,
        common_name=common_name,
        reason_code=reason,
        reasoning=rationale,
        adjudicated_by=actor,
        adjudicator_role=normalized_role,
        policy_version=policy,
        evidence=evidence_items,
        supersedes_adjudication_id=supersedes_adjudication_id,
        adjudication_identity=supplied_identity,
    )
    existing = connection.execute(
        """
        SELECT ground_truth_adjudication_id, input_fingerprint
        FROM ground_truth_adjudications WHERE idempotency_key = ?
        """,
        (retry_key,),
    ).fetchone()
    if existing is not None:
        if str(existing[1]) != fingerprint:
            raise ScienceInvariantError(
                "Ground Truth adjudication idempotency key was reused with different inputs"
            )
        return int(existing[0])

    eligibility = evaluate_ground_truth_adjudication_eligibility(
        connection,
        ground_truth_member_id=ground_truth_member_id,
        evidence=evidence_items,
        adjudicated_by=actor,
        adjudicator_role=normalized_role,
        policy_version=policy,
        result=normalized_result,
    )
    if not eligibility.eligible:
        raise ScienceInvariantError(
            "Ground Truth adjudication is ineligible: " + ", ".join(eligibility.reasons)
        )

    if supersedes_adjudication_id is not None:
        prior = connection.execute(
            """
            SELECT ground_truth_member_id FROM ground_truth_adjudications
            WHERE ground_truth_adjudication_id = ?
            """,
            (supersedes_adjudication_id,),
        ).fetchone()
        if prior is None:
            raise ScienceInvariantError(
                f"Unknown superseded Ground Truth adjudication: {supersedes_adjudication_id}"
            )
        if int(prior[0]) != ground_truth_member_id:
            raise ScienceInvariantError(
                "Ground Truth adjudication supersession must remain within one member"
            )

    identity = supplied_identity or f"ground-truth-adjudication:{uuid.uuid4()}"
    timestamp = created_at or _now()
    connection.execute("SAVEPOINT create_ground_truth_adjudication")
    try:
        cursor = connection.execute(
            """
            INSERT INTO ground_truth_adjudications (
                adjudication_identity, ground_truth_member_id, result,
                adjudicated_scientific_name, adjudicated_common_name,
                reason_code, reasoning, adjudicated_by, adjudicator_role,
                policy_version, supersedes_adjudication_id, input_fingerprint,
                idempotency_key, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identity,
                ground_truth_member_id,
                normalized_result.value,
                scientific_name,
                common_name,
                reason,
                rationale,
                actor,
                normalized_role.value,
                policy,
                supersedes_adjudication_id,
                fingerprint,
                retry_key,
                timestamp,
            ),
        )
        if cursor.lastrowid is None:
            raise ScienceInvariantError("Ground Truth adjudication did not return an ID")
        adjudication_id = int(cursor.lastrowid)
        for item in evidence_items:
            connection.execute(
                """
                INSERT INTO ground_truth_adjudication_evidence (
                    ground_truth_adjudication_id, evidence_id,
                    relationship_role, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (adjudication_id, item.evidence_id, item.role.value, timestamp),
            )
        for recording_id in eligibility.required_recording_ids:
            add_recording_protection(
                connection,
                recording_id=recording_id,
                protection_type=ProtectionType.GROUND_TRUTH_EVIDENCE,
                origin_type=ProtectionOrigin.GROUND_TRUTH,
                origin_reference=identity,
                reason_code="GROUND_TRUTH_ADJUDICATION_EVIDENCE",
                reason="Required bounded source Evidence for Ground Truth adjudication.",
                created_by=actor,
                created_at=timestamp,
            )
        connection.execute("RELEASE SAVEPOINT create_ground_truth_adjudication")
        return adjudication_id
    except (sqlite3.Error, ScienceInvariantError) as error:
        connection.execute("ROLLBACK TO SAVEPOINT create_ground_truth_adjudication")
        connection.execute("RELEASE SAVEPOINT create_ground_truth_adjudication")
        if isinstance(error, ScienceInvariantError):
            raise
        raise ScienceInvariantError(str(error)) from error


def get_ground_truth_adjudication(
    connection: sqlite3.Connection,
    ground_truth_adjudication_id: int,
) -> GroundTruthAdjudicationRecord | None:
    row = connection.execute(
        f"SELECT {ADJUDICATION_COLUMNS} FROM ground_truth_adjudications "
        "WHERE ground_truth_adjudication_id = ?",
        (ground_truth_adjudication_id,),
    ).fetchone()
    return GroundTruthAdjudicationRecord(*row) if row is not None else None


def get_ground_truth_adjudication_evidence(
    connection: sqlite3.Connection,
    ground_truth_adjudication_id: int,
) -> list[GroundTruthAdjudicationEvidenceRecord]:
    rows = connection.execute(
        """
        SELECT ground_truth_adjudication_evidence_id,
               ground_truth_adjudication_id, evidence_id,
               relationship_role, created_at
        FROM ground_truth_adjudication_evidence
        WHERE ground_truth_adjudication_id = ?
        ORDER BY ground_truth_adjudication_evidence_id
        """,
        (ground_truth_adjudication_id,),
    ).fetchall()
    return [GroundTruthAdjudicationEvidenceRecord(*row) for row in rows]


def list_ground_truth_adjudication_history(
    connection: sqlite3.Connection,
    ground_truth_member_id: int,
) -> list[GroundTruthAdjudicationRecord]:
    rows = connection.execute(
        f"""
        SELECT {ADJUDICATION_COLUMNS}
        FROM ground_truth_adjudications
        WHERE ground_truth_member_id = ?
        ORDER BY created_at, ground_truth_adjudication_id
        """,
        (ground_truth_member_id,),
    ).fetchall()
    return [GroundTruthAdjudicationRecord(*row) for row in rows]


def list_current_ground_truth_adjudications(
    connection: sqlite3.Connection,
    ground_truth_member_id: int,
) -> list[GroundTruthAdjudicationRecord]:
    columns = ", ".join(
        f"adjudication.{column.strip()}" for column in ADJUDICATION_COLUMNS.split(",")
    )
    rows = connection.execute(
        f"""
        SELECT {columns}
        FROM ground_truth_adjudications AS adjudication
        WHERE adjudication.ground_truth_member_id = ?
          AND NOT EXISTS (
              SELECT 1 FROM ground_truth_adjudications AS replacement
              WHERE replacement.supersedes_adjudication_id =
                    adjudication.ground_truth_adjudication_id
          )
        ORDER BY adjudication.created_at,
                 adjudication.ground_truth_adjudication_id
        """,
        (ground_truth_member_id,),
    ).fetchall()
    return [GroundTruthAdjudicationRecord(*row) for row in rows]
