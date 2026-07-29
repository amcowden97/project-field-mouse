from __future__ import annotations

import math

import numpy as np
import soundfile as sf

from app.verification.models import DetectionContext, PluginResult, Verdict
from app.verification.plugin import VerificationPlugin


class AudioQualityPlugin(VerificationPlugin):
    name = "audio_quality"

    def __init__(self, *, weight: float = 0.50) -> None:
        self.weight = weight

    def verify(self, context: DetectionContext) -> PluginResult:
        info = sf.info(context.audio_path)
        start_frame = max(0, int((context.start_time or 0.0) * info.samplerate))
        stop_frame = (
            min(info.frames, int(context.end_time * info.samplerate))
            if context.end_time is not None
            else info.frames
        )
        audio, sample_rate = sf.read(
            context.audio_path,
            start=start_frame,
            stop=max(start_frame, stop_frame),
            always_2d=False,
        )
        del sample_rate
        samples = np.asarray(audio, dtype=float)
        if samples.ndim > 1:
            samples = np.mean(samples, axis=1)
        if samples.size == 0:
            return self._result("oppose", 0.99, "Recording is empty.", {})

        peak = float(np.max(np.abs(samples)))
        rms = float(np.sqrt(np.mean(samples**2)))
        clipping = float(np.mean(np.abs(samples) >= 0.99))
        silence = float(np.mean(np.abs(samples) < 0.002))
        frame_size = min(2048, samples.size)
        frame_count = samples.size // frame_size
        if frame_count:
            frames = samples[: frame_count * frame_size].reshape(
                frame_count, frame_size
            )
            frame_rms = np.sqrt(np.mean(frames**2, axis=1))
            noise_floor = float(np.percentile(frame_rms, 20))
        else:
            noise_floor = rms
        snr_db = (
            20.0 * math.log10(max(rms, 1e-9) / max(noise_floor, 1e-9))
        )
        details = {
            "rms": round(rms, 6),
            "peak": round(peak, 6),
            "clipping_fraction": round(clipping, 6),
            "silence_fraction": round(silence, 6),
            "estimated_snr_db": round(snr_db, 2),
        }
        if clipping > 0.01:
            return self._result(
                "oppose", 0.90, "Audio is substantially clipped.", details
            )
        if silence > 0.95 or rms < 0.001:
            return self._result(
                "oppose", 0.95, "Audio is mostly silent.", details
            )
        if snr_db < 3.0:
            return self._result(
                "oppose", 0.75, "Audio has a poor estimated signal-to-noise ratio.", details
            )
        if snr_db >= 10.0 and clipping < 0.001:
            return self._result(
                "support", 0.85, "Audio quality is excellent.", details
            )
        return self._result(
            "neutral", 0.5, "Audio quality is usable but not strongly informative.", details
        )

    def _result(
        self,
        verdict: Verdict,
        score: float,
        reason: str,
        details: dict[str, float],
    ) -> PluginResult:
        return PluginResult(self.name, verdict, score, self.weight, reason, details)
