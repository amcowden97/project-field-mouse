from __future__ import annotations

from dataclasses import dataclass

from app.verification.models import DetectionContext, PluginResult
from app.verification.plugin import VerificationPlugin


@dataclass(frozen=True)
class GeographicOccurrence:
    status: str
    score: float
    note: str = ""


class GeographicPlugin(VerificationPlugin):
    name = "geographic"

    def __init__(
        self,
        occurrences: dict[str, GeographicOccurrence],
        *,
        region_name: str,
        weight: float = 0.65,
    ) -> None:
        self.occurrences = {
            species.casefold(): occurrence
            for species, occurrence in occurrences.items()
        }
        self.region_name = region_name
        self.weight = weight

    def verify(self, context: DetectionContext) -> PluginResult:
        keys = [context.common_name.casefold()]
        if context.scientific_name:
            keys.insert(0, context.scientific_name.casefold())
        occurrence = next(
            (self.occurrences[key] for key in keys if key in self.occurrences),
            None,
        )
        if occurrence is None:
            return PluginResult(
                self.name,
                "neutral",
                0.5,
                0.0,
                f"No curated occurrence data for {context.common_name} in "
                f"{self.region_name}; geography did not affect confidence.",
                {"region": self.region_name, "status": "unknown"},
            )
        verdict = (
            "support"
            if occurrence.status in {"common", "resident", "expected"}
            else "oppose"
            if occurrence.status in {"rare", "vagrant", "absent"}
            else "neutral"
        )
        return PluginResult(
            self.name,
            verdict,
            occurrence.score,
            self.weight,
            f"{context.common_name} is {occurrence.status} in "
            f"{self.region_name}.",
            {
                "region": self.region_name,
                "status": occurrence.status,
                "note": occurrence.note,
            },
        )

