from __future__ import annotations

from dataclasses import dataclass

from app.verification.models import DetectionContext, PluginResult
from app.verification.plugin import VerificationPlugin


@dataclass(frozen=True)
class SeasonalPattern:
    expected_months: frozenset[int]
    active_hours: tuple[int, int] | None = None
    note: str = ""


class SeasonalPlugin(VerificationPlugin):
    name = "seasonal"

    def __init__(
        self,
        patterns: dict[str, SeasonalPattern],
        *,
        weight: float = 0.55,
    ) -> None:
        self.patterns = {
            species.casefold(): pattern for species, pattern in patterns.items()
        }
        self.weight = weight

    def verify(self, context: DetectionContext) -> PluginResult:
        keys = [context.common_name.casefold()]
        if context.scientific_name:
            keys.insert(0, context.scientific_name.casefold())
        pattern = next(
            (self.patterns[key] for key in keys if key in self.patterns),
            None,
        )
        if pattern is None:
            return PluginResult(
                self.name,
                "neutral",
                0.5,
                0.0,
                f"No seasonal profile for {context.common_name}; season did "
                "not affect confidence.",
            )
        month_expected = context.recorded_at.month in pattern.expected_months
        time_expected = True
        if pattern.active_hours:
            start, end = pattern.active_hours
            hour = context.recorded_at.hour
            time_expected = (
                start <= hour < end
                if start < end
                else hour >= start or hour < end
            )
        if month_expected and time_expected:
            return PluginResult(
                self.name,
                "support",
                0.80,
                self.weight,
                f"Month and time are expected for {context.common_name}.",
                {"month_expected": True, "time_expected": True},
            )
        penalty = 0.85 if not month_expected else 0.65
        reason = (
            f"Month {context.recorded_at.month} is outside the expected "
            f"season for {context.common_name}."
            if not month_expected
            else f"The detection time is unusual for {context.common_name}."
        )
        return PluginResult(
            self.name,
            "oppose",
            penalty,
            self.weight if not month_expected else self.weight * 0.35,
            reason,
            {
                "month_expected": month_expected,
                "time_expected": time_expected,
                "note": pattern.note,
            },
        )
