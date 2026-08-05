from __future__ import annotations

from dataclasses import dataclass

from app.verification.models import DetectionContext, RuleOutcome


@dataclass(frozen=True)
class RuleConfig:
    reject_below: float = 0.40
    verify_below: float = 0.95

    def __post_init__(self) -> None:
        if not 0.0 <= self.reject_below <= self.verify_below <= 1.0:
            raise ValueError("Rule thresholds must satisfy 0 <= reject <= verify <= 1.")


class RuleEngine:
    def __init__(self, config: RuleConfig | None = None) -> None:
        self.config = config or RuleConfig()

    def evaluate(self, context: DetectionContext) -> RuleOutcome:
        confidence = context.birdnet_confidence
        if confidence < self.config.reject_below:
            return RuleOutcome(
                "reject",
                f"BirdNET confidence {confidence:.0%} is below the "
                f"{self.config.reject_below:.0%} rejection threshold.",
                "birdnet_reject_threshold",
            )
        if confidence >= self.config.verify_below:
            return RuleOutcome(
                "verify",
                f"BirdNET confidence {confidence:.0%} provides a strong prior; "
                "independent evidence is still evaluated.",
                "birdnet_strong_prior",
            )
        return RuleOutcome(
            "verify",
            f"BirdNET confidence {confidence:.0%} requires corroboration.",
            "birdnet_verification_band",
        )
