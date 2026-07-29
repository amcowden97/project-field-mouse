from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
import subprocess

from app.verification.models import DetectionContext, PluginResult
from app.verification.plugin import VerificationPlugin


@dataclass(frozen=True)
class SecondModelPrediction:
    scientific_name: str | None
    common_name: str
    confidence: float
    model_version: str


class SecondModelAdapter(VerificationPlugin, ABC):
    """Stable boundary for Perch, ONNX, TFLite, or remote classifiers."""

    name = "second_model"
    weight = 1.25

    @abstractmethod
    def predict(self, context: DetectionContext) -> SecondModelPrediction:
        """Run a model on the detection's exact audio interval."""

    def verify(self, context: DetectionContext) -> PluginResult:
        prediction = self.predict(context)
        expected = (
            context.scientific_name.casefold()
            if context.scientific_name
            else context.common_name.casefold()
        )
        observed = (
            prediction.scientific_name.casefold()
            if prediction.scientific_name
            else prediction.common_name.casefold()
        )
        agrees = expected == observed
        return PluginResult(
            plugin=self.name,
            verdict="support" if agrees else "oppose",
            score=prediction.confidence,
            weight=self.weight,
            reason=(
                f"Second model {prediction.model_version} "
                f"{'agrees' if agrees else 'disagrees'} "
                f"({prediction.common_name}, {prediction.confidence:.0%})."
            ),
            details={
                "scientific_name": prediction.scientific_name,
                "common_name": prediction.common_name,
                "confidence": prediction.confidence,
                "model_version": prediction.model_version,
                "species_agreement": agrees,
            },
        )


class PerchCommandAdapter(SecondModelAdapter):
    """Optional process-isolated adapter for a pinned Perch runtime."""

    name = "second_model"

    def __init__(
        self,
        command: list[str],
        *,
        model_version: str,
        timeout_seconds: float = 60.0,
        weight: float = 1.25,
    ) -> None:
        if not command:
            raise ValueError("Perch command cannot be empty.")
        self.command = tuple(command)
        self.model_version = model_version
        self.timeout_seconds = timeout_seconds
        self.weight = weight

    def predict(self, context: DetectionContext) -> SecondModelPrediction:
        request = {
            "audio_path": str(context.audio_path),
            "start_time": context.start_time,
            "end_time": context.end_time,
            "expected_scientific_name": context.scientific_name,
        }
        completed = subprocess.run(
            self.command,
            input=json.dumps(request),
            capture_output=True,
            check=True,
            text=True,
            timeout=self.timeout_seconds,
        )
        response = json.loads(completed.stdout)
        return SecondModelPrediction(
            scientific_name=response.get("scientific_name"),
            common_name=str(response["common_name"]),
            confidence=float(response["confidence"]),
            model_version=str(response.get("model_version", self.model_version)),
        )
