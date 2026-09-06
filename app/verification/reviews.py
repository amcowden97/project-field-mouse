from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal


ReviewState = Literal[
    "pending_review",
    "verified",
    "rejected",
    "corrected_species",
    "ignored",
]


@dataclass(frozen=True)
class ReviewInput:
    detection_id: int
    state: ReviewState
    reviewer: str
    notes: str = ""
    corrected_scientific_name: str | None = None
    corrected_common_name: str | None = None
    confidence_after: float | None = None
    evidence_ids: tuple[int, ...] = ()
    reviewer_role: Literal["USER", "EXPERT"] = "USER"
    reason_code: str = "OPERATOR_REVIEW"


def record_review(
    connection: sqlite3.Connection,
    review: ReviewInput,
    *,
    reviewed_at: datetime | None = None,
) -> int:
    if not review.reviewer.strip():
        raise ValueError("Reviewer is required.")
    if review.state == "corrected_species" and not (
        review.corrected_scientific_name or review.corrected_common_name
    ):
        raise ValueError("A corrected species is required for a correction.")
    if review.confidence_after is not None and not (
        0.0 <= review.confidence_after <= 1.0
    ):
        raise ValueError("Confidence after review must be between 0 and 1.")

    detection = connection.execute(
        """
        SELECT d.scientific_name, d.common_name, d.confidence,
               v.consensus_score
        FROM detections AS d
        LEFT JOIN verifications AS v ON v.detection_id = d.id
        WHERE d.id = ?
        """,
        (review.detection_id,),
    ).fetchone()
    if detection is None:
        raise ValueError(f"Detection {review.detection_id} does not exist.")
    confidence_before = (
        detection["consensus_score"]
        if detection["consensus_score"] is not None
        else detection["confidence"]
    )
    now = (reviewed_at or datetime.now(timezone.utc)).isoformat()
    legacy_status = {
        "pending_review": "unreviewed",
        "verified": "confirmed",
        "rejected": "dismissed",
        "corrected_species": "corrected",
        "ignored": "dismissed",
    }[review.state]
    canonical_decisions = {
        "verified": "CONFIRM",
        "rejected": "REJECT",
        "corrected_species": "CORRECT_TAXON",
    }
    if review.evidence_ids and review.state not in canonical_decisions:
        raise ValueError(
            "Only conclusive legacy review states can create a canonical Review."
        )

    connection.execute("SAVEPOINT legacy_review_compatibility")
    try:
        cursor = connection.execute(
            """
            INSERT INTO detection_reviews (
                detection_id, review_state, reviewed_at, reviewer,
                original_scientific_name, original_common_name,
                corrected_scientific_name, corrected_common_name, notes,
                confidence_before, confidence_after, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review.detection_id,
                review.state,
                now,
                review.reviewer.strip(),
                detection["scientific_name"],
                detection["common_name"],
                review.corrected_scientific_name,
                review.corrected_common_name,
                review.notes,
                confidence_before,
                review.confidence_after,
                now,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("Review was saved but no ID was returned.")
        legacy_review_id = int(cursor.lastrowid)
        connection.execute(
            """
            UPDATE verifications
            SET review_status = ?, updated_at = ?
            WHERE detection_id = ?
            """,
            (legacy_status, now, review.detection_id),
        )
        canonical_schema = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'reviews'"
        ).fetchone()
        if canonical_schema and review.evidence_ids:
            from app.science.reviews import (
                ReviewDecision,
                ReviewEvidenceInput,
                ReviewEvidenceRole,
                ReviewerRole,
                create_review,
            )

            evidence = tuple(
                ReviewEvidenceInput(
                    evidence_id,
                    (
                        ReviewEvidenceRole.PRIMARY
                        if index == 0
                        else ReviewEvidenceRole.SUPPORTING
                    ),
                )
                for index, evidence_id in enumerate(review.evidence_ids)
            )
            create_review(
                connection,
                detection_id=review.detection_id,
                decision=ReviewDecision(canonical_decisions[review.state]),
                reviewer_identity=review.reviewer,
                reviewer_role=ReviewerRole(review.reviewer_role),
                reviewed_at=now,
                reason_code=review.reason_code,
                evidence=evidence,
                notes=review.notes,
                proposed_scientific_name=review.corrected_scientific_name,
                proposed_common_name=review.corrected_common_name,
                legacy_detection_review_id=legacy_review_id,
                created_at=now,
            )
        connection.execute("RELEASE SAVEPOINT legacy_review_compatibility")
        return legacy_review_id
    except Exception:
        connection.execute("ROLLBACK TO SAVEPOINT legacy_review_compatibility")
        connection.execute("RELEASE SAVEPOINT legacy_review_compatibility")
        raise
