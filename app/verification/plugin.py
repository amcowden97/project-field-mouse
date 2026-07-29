from __future__ import annotations

from abc import ABC, abstractmethod

from app.verification.models import DetectionContext, PluginResult


class VerificationPlugin(ABC):
    """Contract implemented by every independent evidence source."""

    name: str

    @abstractmethod
    def verify(self, context: DetectionContext) -> PluginResult:
        """Evaluate a detection without mutating it."""

