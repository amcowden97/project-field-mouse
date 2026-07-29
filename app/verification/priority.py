from __future__ import annotations

from dataclasses import replace

from app.verification.models import DetectionContext, VerificationDecision


def apply_review_priority(
    context: DetectionContext,
    decision: VerificationDecision,
) -> VerificationDecision:
    """Flag unusual observations for review without changing their score."""
    flags: set[str] = set()
    for result in decision.plugin_results:
        if result.plugin == "geographic" and result.verdict == "oppose":
            status = str(result.details.get("status", "unexpected"))
            flags.add(f"regional_{status}")
        if result.plugin == "seasonal" and result.verdict == "oppose":
            if result.details.get("month_expected") is False:
                flags.add("out_of_season")
            if result.details.get("time_expected") is False:
                flags.add("unexpected_time")
        if result.plugin == "historical":
            count = int(result.details.get("verified_observation_count", 0))
            if count == 0:
                flags.add("new_station_species")
        if result.plugin == "second_model" and result.verdict == "oppose":
            flags.add("model_disagreement")

    priority = min(100, 20 * len(flags))
    if decision.status == "uncertain":
        priority = min(100, priority + 20)
    evidence = tuple(
        {
            "source": result.plugin,
            "outcome": result.verdict,
            "score": result.score,
            "weight": result.weight,
            "summary": result.reason,
            "details": result.details,
        }
        for result in decision.plugin_results
    )
    evidence = (
        {
            "source": "birdnet",
            "outcome": "support",
            "score": context.birdnet_confidence,
            "weight": 1.0,
            "summary": (
                f"BirdNET proposed {context.common_name} at "
                f"{context.birdnet_confidence:.0%}."
            ),
            "details": {},
        },
        *evidence,
    )
    return replace(
        decision,
        evidence=evidence,
        review_priority=priority,
        review_flags=tuple(sorted(flags)),
    )
