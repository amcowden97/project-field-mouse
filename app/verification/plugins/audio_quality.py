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
        spectrum = np.abs(np.fft.rfft(samples[: min(samples.size, sample_rate * 10)]))
        frequencies = np.fft.rfftfreq(
            min(samples.size, sample_rate * 10), d=1.0 / sample_rate
        )
        power = spectrum**2
        total_power = float(np.sum(power)) + 1e-12

        def band_ratio(low: float, high: float) -> float:
            selected = (frequencies >= low) & (frequencies < high)
            return float(np.sum(power[selected]) / total_power)

        low_frequency_ratio = band_ratio(0, 250)
        speech_band_ratio = band_ratio(250, 4000)
        high_frequency_ratio = band_ratio(4000, sample_rate / 2)
        nonzero = spectrum[spectrum > 1e-12]
        spectral_flatness = (
            float(
                np.exp(np.mean(np.log(nonzero)))
                / max(np.mean(nonzero), 1e-12)
            )
            if nonzero.size
            else 0.0
        )
        frame_variability = (
            float(np.std(frame_rms) / max(np.mean(frame_rms), 1e-9))
            if frame_count
            else 0.0
        )
        interference = {
            "wind": round(
                min(1.0, low_frequency_ratio / 0.60), 3
            ),
            "rain": round(
                min(1.0, spectral_flatness * high_frequency_ratio * 4.0), 3
            ),
            "vehicle": round(
                min(
                    1.0,
                    low_frequency_ratio
                    * max(0.0, 1.0 - frame_variability)
                    * 2.0,
                ),
                3,
            ),
            "speech_or_vocalization": round(
                min(1.0, speech_band_ratio * frame_variability * 1.5), 3
            ),
            "running_water": round(
                min(
                    1.0,
                    spectral_flatness
                    * max(0.0, 1.0 - frame_variability)
                    * 2.0,
                ),
                3,
            ),
        }
        details = {
            "rms": round(rms, 6),
            "peak": round(peak, 6),
            "clipping_fraction": round(clipping, 6),
            "silence_fraction": round(silence, 6),
            "estimated_snr_db": round(snr_db, 2),
            "low_frequency_ratio": round(low_frequency_ratio, 4),
            "speech_band_ratio": round(speech_band_ratio, 4),
            "high_frequency_ratio": round(high_frequency_ratio, 4),
            "spectral_flatness": round(spectral_flatness, 4),
            "frame_variability": round(frame_variability, 4),
            "interference_likelihoods": interference,
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
                "oppose",
                0.75,
                "Audio has a poor estimated signal-to-noise ratio.",
                details,
            )
        likely_interference = max(
            interference["wind"],
            interference["rain"],
            interference["vehicle"],
            interference["running_water"],
        )
        if likely_interference >= 0.75:
            return self._result(
                "oppose",
                0.70,
                "Persistent environmental or mechanical noise may mask calls.",
                details,
            )
        if snr_db >= 10.0 and clipping < 0.001:
            return self._result(
                "support", 0.85, "Audio quality is excellent.", details
            )
        return self._result(
            "neutral",
            0.5,
            "Audio quality is usable but not strongly informative.",
            details,
        )

    def _result(
        self,
        verdict: Verdict,
        score: float,
        reason: str,
        details: dict[str, float],
    ) -> PluginResult:
        return PluginResult(self.name, verdict, score, self.weight, reason, details)
