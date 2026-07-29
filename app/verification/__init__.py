"""Explainable, plugin-based verification for wildlife detections."""

from app.verification.consensus import ConsensusEngine
from app.verification.manager import VerificationManager
from app.verification.models import DetectionContext, VerificationDecision

__all__ = [
    "ConsensusEngine",
    "DetectionContext",
    "VerificationDecision",
    "VerificationManager",
]
