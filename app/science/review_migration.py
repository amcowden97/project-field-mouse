"""Deterministic RC1.1 human-review provenance backfill."""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone


DECISION_BY_LEGACY_STATE = {
    "verified": "CONFIRM",
    "rejected": "REJECT",
    "corrected_species": "CORRECT_TAXON",
}
NON_CONCLUSIVE_STATES = frozenset({"pending_review", "ignored"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def backfill_legacy_reviews(
    connection: sqlite3.Connection,
    *,
    migration_version: int,
) -> dict[str, int | float | list[str]]:
    """Import only defensible legacy conclusions without fabricating Evidence."""
    started_at = _now()
    started = time.perf_counter()
    rows = connection.execute(
        """
        SELECT id, detection_id, review_state, reviewed_at, reviewer,
               corrected_scientific_name, corrected_common_name, notes, created_at
        FROM detection_reviews
        ORDER BY id
        """
    ).fetchall()
    migrated = 0
    skipped_non_conclusive = 0
    ambiguous = 0
    invalid = 0

    for row in rows:
        legacy_id = int(row[0])
        detection_id = int(row[1])
        state = str(row[2])
        reviewer = str(row[4]).strip()
        proposed_scientific_name = row[5]
        proposed_common_name = row[6]

        if connection.execute(
            "SELECT 1 FROM reviews WHERE legacy_detection_review_id = ?",
            (legacy_id,),
        ).fetchone():
            continue
        if state in NON_CONCLUSIVE_STATES:
            skipped_non_conclusive += 1
            continue
        decision = DECISION_BY_LEGACY_STATE.get(state)
        if decision is None:
            ambiguous += 1
            continue
        if not reviewer or not connection.execute(
            "SELECT 1 FROM detections WHERE id = ?", (detection_id,)
        ).fetchone():
            invalid += 1
            continue
        if decision == "CORRECT_TAXON" and not (
            str(proposed_scientific_name or "").strip()
            or str(proposed_common_name or "").strip()
        ):
            invalid += 1
            continue

        connection.execute(
            """
            INSERT INTO reviews (
                review_identity, detection_id, decision, reviewer_identity,
                reviewer_role, reviewed_at, reason_code, notes,
                proposed_scientific_name, proposed_common_name,
                legacy_detection_review_id, created_at
            ) VALUES (?, ?, ?, ?, 'LEGACY_IMPORT', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"legacy-detection-review:{legacy_id:020d}",
                detection_id,
                decision,
                reviewer,
                str(row[3]),
                f"RC1_1_{state.upper()}",
                str(row[7] or ""),
                proposed_scientific_name,
                proposed_common_name,
                legacy_id,
                str(row[8]),
            ),
        )
        migrated += 1

    elapsed_ms = (time.perf_counter() - started) * 1000
    warnings = []
    if ambiguous:
        warnings.append(f"{ambiguous} legacy review state(s) were ambiguous")
    if invalid:
        warnings.append(f"{invalid} conclusive legacy review(s) were invalid")
    completed_at = _now()
    connection.execute(
        """
        INSERT INTO review_schema_migration_runs (
            migration_version, started_at, completed_at, total_legacy_reviews,
            migrated_count, skipped_non_conclusive_count, ambiguous_count,
            invalid_count, backfill_ms, warnings_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            migration_version,
            started_at,
            completed_at,
            len(rows),
            migrated,
            skipped_non_conclusive,
            ambiguous,
            invalid,
            elapsed_ms,
            json.dumps(warnings, separators=(",", ":")),
        ),
    )
    return {
        "total_legacy_reviews": len(rows),
        "migrated": migrated,
        "skipped_non_conclusive": skipped_non_conclusive,
        "ambiguous": ambiguous,
        "invalid": invalid,
        "backfill_ms": elapsed_ms,
        "warnings": warnings,
    }
