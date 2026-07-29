from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal


Verdict = Literal["support", "neutral", "oppose"]
Status = Literal["verified", "probable", "uncertain", "rejected"]


@dataclass(frozen=True)
class DetectionContext:
    detection_id: int | None
    recording_id: int
    station_id: str
    scientific_name: str | None
    common_name: str
    birdnet_confidence: float
    recorded_at: datetime
    audio_path: Path
    start_time: float | None = None
    end_time: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PluginResult:
    plugin: str
    verdict: Verdict
    score: float
    weight: float
    reason: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("Plugin score must be between 0 and 1.")
        if self.weight < 0.0:
            raise ValueError("Plugin weight cannot be negative.")


@dataclass(frozen=True)
class RuleOutcome:
    action: Literal["accept", "reject", "verify"]
    reason: str
    rule: str


@dataclass(frozen=True)
class VerificationDecision:
    score: float
    status: Status
    reason: str
    explanation: tuple[str, ...]
    plugin_results: tuple[PluginResult, ...]
    rule_outcome: RuleOutcome

