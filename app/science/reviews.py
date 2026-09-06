"""Canonical, append-only human Review provenance operations."""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Iterable

from app.science import ScienceInvariantError


class ReviewDecision(StrEnum):
    CONFIRM = "CONFIRM"
    REJECT = "REJECT"
    UNSURE = "UNSURE"
    CORRECT_TAXON = "CORRECT_TAXON"


class ReviewerRole(StrEnum):
    USER = "USER"
    EXPERT = "EXPERT"
    LEGACY_IMPORT = "LEGACY_IMPORT"


class ReviewEvidenceRole(StrEnum):
    PRIMARY = "PRIMARY"
    SUPPORTING = "SUPPORTING"
    CONTEXT = "CONTEXT"


@dataclass(frozen=True)
class ReviewEvidenceInput:
    evidence_id: int
    role: ReviewEvidenceRole


@dataclass(frozen=True)
class ReviewRecord:
    review_id: int
    review_identity: str
    detection_id: int
    decision: str
    reviewer_identity: str
    reviewer_role: str
    reviewed_at: str
    reason_code: str
    notes: str
    proposed_scientific_name: str | None
    proposed_common_name: str | None
    supersedes_review_id: int | None
    legacy_detection_review_id: int | None
    created_at: str


@dataclass(frozen=True)
class ReviewEvidenceRecord:
    review_evidence_id: int
    review_id: int
    evidence_id: int
    relationship_role: str
    created_at: str


REVIEW_COLUMNS = """
review_id, review_identity, detection_id, decision, reviewer_identity,
reviewer_role, reviewed_at, reason_code, notes, proposed_scientific_name,
proposed_common_name, supersedes_review_id, legacy_detection_review_id, created_at
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _review_record(row: tuple | sqlite3.Row) -> ReviewRecord:
    return ReviewRecord(*row)


def create_review(
    connection: sqlite3.Connection,
    *,
    detection_id: int,
    decision: ReviewDecision,
    reviewer_identity: str,
    reviewer_role: ReviewerRole,
    reviewed_at: str,
    reason_code: str,
    evidence: Iterable[ReviewEvidenceInput] = (),
    notes: str = "",
    proposed_scientific_name: str | None = None,
    proposed_common_name: str | None = None,
    supersedes_review_id: int | None = None,
    legacy_detection_review_id: int | None = None,
    review_identity: str | None = None,
    created_at: str | None = None,
) -> int:
    """Create one Review and its explicit Evidence relationships atomically."""
    if not reviewer_identity.strip():
        raise ScienceInvariantError("Reviewer identity is required")
    if not reason_code.strip():
        raise ScienceInvariantError("Review reason code is required")
    if not connection.execute(
        "SELECT 1 FROM detections WHERE id = ?", (detection_id,)
    ).fetchone():
        raise ScienceInvariantError(f"Unknown Detection: {detection_id}")
    if decision is ReviewDecision.CORRECT_TAXON:
        if not (
            str(proposed_scientific_name or "").strip()
            or str(proposed_common_name or "").strip()
        ):
            raise ScienceInvariantError("CORRECT_TAXON requires a proposed taxon")
    elif proposed_scientific_name is not None or proposed_common_name is not None:
        raise ScienceInvariantError("Only CORRECT_TAXON may propose a taxon")

    evidence_items = tuple(evidence)
    if reviewer_role in {ReviewerRole.USER, ReviewerRole.EXPERT} and not evidence_items:
        raise ScienceInvariantError("New USER and EXPERT Reviews require Evidence")
    if reviewer_role is ReviewerRole.LEGACY_IMPORT and legacy_detection_review_id is None:
        raise ScienceInvariantError("LEGACY_IMPORT requires legacy provenance")
    if legacy_detection_review_id is not None:
        legacy = connection.execute(
            "SELECT detection_id FROM detection_reviews WHERE id = ?",
            (legacy_detection_review_id,),
        ).fetchone()
        if legacy is None:
            raise ScienceInvariantError(
                f"Unknown legacy Detection Review: {legacy_detection_review_id}"
            )
        if int(legacy[0]) != detection_id:
            raise ScienceInvariantError(
                "Legacy Review provenance must belong to the reviewed Detection"
            )
    seen: set[int] = set()
    for item in evidence_items:
        if item.evidence_id in seen:
            raise ScienceInvariantError("Duplicate ReviewEvidence")
        seen.add(item.evidence_id)
        row = connection.execute(
            "SELECT detection_id FROM evidence WHERE evidence_id = ?",
            (item.evidence_id,),
        ).fetchone()
        if row is None:
            raise ScienceInvariantError(f"Unknown Evidence: {item.evidence_id}")
        if int(row[0]) != detection_id:
            raise ScienceInvariantError(
                "ReviewEvidence must belong to the reviewed Detection"
            )

    if supersedes_review_id is not None:
        prior = connection.execute(
            "SELECT detection_id FROM reviews WHERE review_id = ?",
            (supersedes_review_id,),
        ).fetchone()
        if prior is None:
            raise ScienceInvariantError(f"Unknown superseded Review: {supersedes_review_id}")
        if int(prior[0]) != detection_id:
            raise ScienceInvariantError("Supersession must remain within one Detection")

    timestamp = created_at or _now()
    identity = review_identity or f"review:{uuid.uuid4()}"
    connection.execute("SAVEPOINT create_scientific_review")
    try:
        cursor = connection.execute(
            """
            INSERT INTO reviews (
                review_identity, detection_id, decision, reviewer_identity,
                reviewer_role, reviewed_at, reason_code, notes,
                proposed_scientific_name, proposed_common_name,
                supersedes_review_id, legacy_detection_review_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identity,
                detection_id,
                decision.value,
                reviewer_identity.strip(),
                reviewer_role.value,
                reviewed_at,
                reason_code.strip(),
                notes,
                proposed_scientific_name,
                proposed_common_name,
                supersedes_review_id,
                legacy_detection_review_id,
                timestamp,
            ),
        )
        if cursor.lastrowid is None:
            raise ScienceInvariantError("Review did not return an ID")
        review_id = int(cursor.lastrowid)
        for item in evidence_items:
            connection.execute(
                """
                INSERT INTO review_evidence (
                    review_id, evidence_id, relationship_role, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (review_id, item.evidence_id, item.role.value, timestamp),
            )
        connection.execute("RELEASE SAVEPOINT create_scientific_review")
        return review_id
    except (sqlite3.Error, ScienceInvariantError) as error:
        connection.execute("ROLLBACK TO SAVEPOINT create_scientific_review")
        connection.execute("RELEASE SAVEPOINT create_scientific_review")
        if isinstance(error, ScienceInvariantError):
            raise
        raise ScienceInvariantError(str(error)) from error


def get_review(
    connection: sqlite3.Connection,
    review_id: int,
) -> ReviewRecord | None:
    row = connection.execute(
        f"SELECT {REVIEW_COLUMNS} FROM reviews WHERE review_id = ?",
        (review_id,),
    ).fetchone()
    return _review_record(row) if row is not None else None


def list_review_history(
    connection: sqlite3.Connection,
    detection_id: int,
) -> list[ReviewRecord]:
    rows = connection.execute(
        f"""
        SELECT {REVIEW_COLUMNS}
        FROM reviews
        WHERE detection_id = ?
        ORDER BY reviewed_at, review_id
        """,
        (detection_id,),
    ).fetchall()
    return [_review_record(row) for row in rows]


def list_current_reviews(
    connection: sqlite3.Connection,
    detection_id: int,
) -> list[ReviewRecord]:
    """Return every non-superseded Review; disagreement remains visible."""
    rows = connection.execute(
        f"""
        SELECT {', '.join(f'review.{column.strip()}' for column in REVIEW_COLUMNS.split(','))}
        FROM reviews AS review
        WHERE review.detection_id = ?
          AND NOT EXISTS (
              SELECT 1 FROM reviews AS replacement
              WHERE replacement.supersedes_review_id = review.review_id
          )
        ORDER BY review.reviewed_at, review.review_id
        """,
        (detection_id,),
    ).fetchall()
    return [_review_record(row) for row in rows]


def get_review_evidence(
    connection: sqlite3.Connection,
    review_id: int,
) -> list[ReviewEvidenceRecord]:
    rows = connection.execute(
        """
        SELECT review_evidence_id, review_id, evidence_id,
               relationship_role, created_at
        FROM review_evidence
        WHERE review_id = ?
        ORDER BY review_evidence_id
        """,
        (review_id,),
    ).fetchall()
    return [ReviewEvidenceRecord(*row) for row in rows]
