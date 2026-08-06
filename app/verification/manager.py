from __future__ import annotations

from collections.abc import Iterable

from app.verification.consensus import ConsensusEngine
from app.verification.models import (
    DetectionContext,
    PluginResult,
    VerificationDecision,
)
from app.verification.plugin import VerificationPlugin
from app.verification.priority import apply_review_priority
from app.verification.rules import RuleEngine


class VerificationManager:
    """Orchestrates rule evaluation and plugins without knowing their types."""

    def __init__(
        self,
        plugins: Iterable[VerificationPlugin],
        *,
        rules: RuleEngine | None = None,
        consensus: ConsensusEngine | None = None,
    ) -> None:
        self.plugins = tuple(plugins)
        self.rules = rules or RuleEngine()
        self.consensus = consensus or ConsensusEngine()

    def verify(self, context: DetectionContext) -> VerificationDecision:
        rule = self.rules.evaluate(context)
        results: list[PluginResult] = []
        # Even a strong BirdNET prediction is independently evaluated. Rules
        # may avoid expensive work for rejected low-confidence detections, but
        # they must not turn BirdNET into its own verifier.
        if rule.action != "reject":
            for plugin in self.plugins:
                try:
                    results.append(plugin.verify(context))
                except Exception as error:
                    results.append(
                        PluginResult(
                            plugin=plugin.name,
                            verdict="neutral",
                            score=0.5,
                            weight=0.0,
                            reason=f"{plugin.name} unavailable: {error}",
                            details={
                                "available": False,
                                "error": type(error).__name__,
                            },
                        )
                    )
        decision = self.consensus.decide(context, results, rule)
        return apply_review_priority(context, decision)
