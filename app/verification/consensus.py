from __future__ import annotations

import math

from app.verification.models import (
    DetectionContext,
    PluginResult,
    RuleOutcome,
    VerificationDecision,
)


class ConsensusEngine:
    """Combine independent evidence as weighted log-odds, not an average."""

    def __init__(
        self,
        *,
        birdnet_weight: float = 1.0,
        verified_threshold: float = 0.90,
        probable_threshold: float = 0.70,
        rejected_threshold: float = 0.35,
    ) -> None:
        self.birdnet_weight = birdnet_weight
        self.verified_threshold = verified_threshold
        self.probable_threshold = probable_threshold
        self.rejected_threshold = rejected_threshold

    @staticmethod
    def _logit(value: float) -> float:
        bounded = min(max(value, 0.01), 0.99)
        return math.log(bounded / (1.0 - bounded))

    @staticmethod
    def _sigmoid(value: float) -> float:
        return 1.0 / (1.0 + math.exp(-value))

    def decide(
        self,
        context: DetectionContext,
        results: list[PluginResult],
        rule: RuleOutcome,
    ) -> VerificationDecision:
        explanations = [rule.reason]
        if rule.action == "reject":
            return VerificationDecision(
                context.birdnet_confidence,
                "rejected",
                rule.reason,
                tuple(explanations),
                tuple(results),
                rule,
            )

        evidence = self.birdnet_weight * self._logit(
            context.birdnet_confidence
        )
        for result in results:
            direction = {
                "support": 1.0,
                "neutral": 0.0,
                "oppose": -1.0,
            }[result.verdict]
            strength = abs(self._logit(result.score))
            evidence += direction * result.weight * strength
            explanations.append(result.reason)

        score = self._sigmoid(evidence)
        if score >= self.verified_threshold:
            status = "verified"
        elif score >= self.probable_threshold:
            status = "probable"
        elif score < self.rejected_threshold:
            status = "rejected"
        else:
            status = "uncertain"

        supporting = sum(result.verdict == "support" for result in results)
        opposing = sum(result.verdict == "oppose" for result in results)
        if status == "verified":
            reason = (
                f"{supporting} independent evidence source(s) support the "
                "identification with no decisive contradiction."
            )
        elif status == "rejected":
            reason = (
                f"Contradictory evidence ({opposing} source(s)) outweighs "
                "the original classification."
            )
        else:
            reason = (
                "Available evidence is mixed or insufficient for a verified "
                "identification."
            )
        return VerificationDecision(
            score,
            status,
            reason,
            tuple(explanations),
            tuple(results),
            rule,
        )

