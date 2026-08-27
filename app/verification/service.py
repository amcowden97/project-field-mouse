from __future__ import annotations

import logging
import sqlite3

from app.verification.manager import VerificationManager
from app.verification.models import (
    DetectionContext,
    PluginResult,
    RuleOutcome,
    VerificationDecision,
)
from app.verification.repository import save_verification


LOGGER = logging.getLogger(__name__)


def unavailable_verification(
    context: DetectionContext,
    error: Exception,
) -> VerificationDecision:
    """Describe a failed verification attempt without rejecting BirdNET data."""
    reason = (
        "Verification was unavailable; the BirdNET detection was preserved "
        "for later review."
    )
    result = PluginResult(
        plugin="verification_system",
        verdict="neutral",
        score=0.5,
        weight=0.0,
        reason=reason,
        details={"available": False, "error": type(error).__name__},
    )
    return VerificationDecision(
        score=context.birdnet_confidence,
        status="uncertain",
        reason=reason,
        explanation=(reason,),
        plugin_results=(result,),
        rule_outcome=RuleOutcome(
            action="verify",
            reason=reason,
            rule="verification_unavailable",
        ),
        evidence=(
            {
                "source": "birdnet",
                "available": True,
                "outcome": "support",
                "score": context.birdnet_confidence,
                "weight": 1.0,
                "log_odds_contribution": None,
                "summary": (
                    f"BirdNET proposed {context.common_name} at "
                    f"{context.birdnet_confidence:.0%}."
                ),
                "details": {},
            },
            {
                "source": "verification_system",
                "available": False,
                "outcome": "neutral",
                "score": 0.5,
                "weight": 0.0,
                "log_odds_contribution": 0.0,
                "summary": reason,
                "details": {"error": type(error).__name__},
            },
        ),
        review_priority=40,
        review_flags=("verification_unavailable",),
    )


def verify_detection_safely(
    connection: sqlite3.Connection,
    detection_id: int,
    context: DetectionContext,
    manager: VerificationManager | None,
    initialization_error: Exception | None = None,
) -> None:
    """Persist verification in an isolated savepoint; never lose detection."""
    if manager is None and initialization_error is None:
        return

    failure: Exception | None = None
    connection.execute("SAVEPOINT fieldmouse_verification")
    try:
        if initialization_error is not None:
            decision = unavailable_verification(context, initialization_error)
        else:
            assert manager is not None
            decision = manager.verify(context)
        save_verification(connection, detection_id, decision)
        connection.execute("RELEASE SAVEPOINT fieldmouse_verification")
        return
    except Exception as error:
        failure = error
        connection.execute("ROLLBACK TO SAVEPOINT fieldmouse_verification")
        connection.execute("RELEASE SAVEPOINT fieldmouse_verification")
        LOGGER.exception(
            "Verification failed for detection %s; preserving BirdNET result",
            detection_id,
        )

    # Retain a queryable marker when the verifier failed but persistence still
    # works. If persistence itself is unavailable, logging is the final fallback.
    connection.execute("SAVEPOINT fieldmouse_verification_fallback")
    try:
        assert failure is not None
        save_verification(
            connection,
            detection_id,
            unavailable_verification(context, failure),
        )
        connection.execute("RELEASE SAVEPOINT fieldmouse_verification_fallback")
    except Exception:
        connection.execute(
            "ROLLBACK TO SAVEPOINT fieldmouse_verification_fallback"
        )
        connection.execute(
            "RELEASE SAVEPOINT fieldmouse_verification_fallback"
        )
        LOGGER.exception(
            "Could not persist verification failure for detection %s; "
            "BirdNET result remains preserved",
            detection_id,
        )
