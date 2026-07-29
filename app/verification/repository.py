from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from app.verification.models import VerificationDecision


def save_verification(
    connection: sqlite3.Connection,
    detection_id: int,
    decision: VerificationDecision,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    cursor = connection.execute(
        """
        INSERT INTO verifications (
            detection_id, consensus_score, status, reason,
            explanation_json, rule_action, rule_name, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(detection_id) DO UPDATE SET
            consensus_score = excluded.consensus_score,
            status = excluded.status,
            reason = excluded.reason,
            explanation_json = excluded.explanation_json,
            rule_action = excluded.rule_action,
            rule_name = excluded.rule_name,
            updated_at = excluded.updated_at
        """,
        (
            detection_id,
            decision.score,
            decision.status,
            decision.reason,
            json.dumps(decision.explanation),
            decision.rule_outcome.action,
            decision.rule_outcome.rule,
            now,
            now,
        ),
    )
    row = connection.execute(
        "SELECT id FROM verifications WHERE detection_id = ?",
        (detection_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("Verification was saved but no ID was returned.")
    verification_id = int(row["id"])
    connection.execute(
        "DELETE FROM verification_results WHERE verification_id = ?",
        (verification_id,),
    )
    for result in decision.plugin_results:
        connection.execute(
            """
            INSERT INTO verification_results (
                verification_id, plugin_name, verdict, score, weight,
                reason, output_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                verification_id,
                result.plugin,
                result.verdict,
                result.score,
                result.weight,
                result.reason,
                json.dumps(result.details, sort_keys=True),
                now,
            ),
        )
    return verification_id
