"""Built-in verification plugins."""

from app.verification.plugins.audio_quality import AudioQualityPlugin
from app.verification.plugins.geographic import GeographicPlugin
from app.verification.plugins.historical import HistoricalPlugin
from app.verification.plugins.seasonal import SeasonalPlugin
from app.verification.plugins.second_model import (
    SecondModelAdapter,
    SecondModelPrediction,
)

__all__ = [
    "AudioQualityPlugin",
    "GeographicPlugin",
    "HistoricalPlugin",
    "SeasonalPlugin",
    "SecondModelAdapter",
    "SecondModelPrediction",
]
