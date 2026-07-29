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
    legacy_status = {
        "pending_review": "unreviewed",
        "verified": "confirmed",
        "rejected": "dismissed",
        "corrected_species": "corrected",
        "ignored": "dismissed",
    }[review.state]
    connection.execute(
        """
        UPDATE verifications
        SET review_status = ?, updated_at = ?
        WHERE detection_id = ?
        """,
        (legacy_status, now, review.detection_id),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("Review was saved but no ID was returned.")
    return int(cursor.lastrowid)
