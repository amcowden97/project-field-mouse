from __future__ import annotations

import sqlite3

from app.verification.models import DetectionContext, PluginResult
from app.verification.plugin import VerificationPlugin


class HistoricalPlugin(VerificationPlugin):
    name = "historical"

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        weight: float = 0.45,
        minimum_verified_score: float = 0.80,
        saturation_count: int = 50,
    ) -> None:
        self.connection = connection
        self.weight = weight
        self.minimum_verified_score = minimum_verified_score
        self.saturation_count = saturation_count

    def verify(self, context: DetectionContext) -> PluginResult:
        row = self.connection.execute(
            """
            SELECT COUNT(DISTINCT d.recording_id) AS observation_count
            FROM detections AS d
            JOIN verifications AS v ON v.detection_id = d.id
            JOIN recordings AS r ON r.id = d.recording_id
            WHERE r.station_id = ?
              AND COALESCE(d.scientific_name, d.common_name) =
                  COALESCE(?, ?)
              AND v.status IN ('verified', 'probable')
              AND v.consensus_score >= ?
              AND d.id != COALESCE(?, -1)
            """,
            (
                context.station_id,
                context.scientific_name,
                context.common_name,
                self.minimum_verified_score,
                context.detection_id,
            ),
        ).fetchone()
        count = int(row["observation_count"] if row else 0)
        if count == 0:
            return PluginResult(
                self.name,
                "neutral",
                0.5,
                0.0,
                "No independently verified station history exists; stronger "
                "current evidence is required.",
                {"verified_observation_count": 0},
            )
        score = min(0.90, 0.55 + 0.35 * (count / self.saturation_count))
        return PluginResult(
            self.name,
            "support",
            score,
            self.weight,
            f"{count} previously verified recording(s) support station history.",
            {"verified_observation_count": count},
        )

