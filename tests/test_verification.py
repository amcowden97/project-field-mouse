from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np

from app.database.migrations import apply_migrations
from app.verification.consensus import ConsensusEngine
from app.verification.manager import VerificationManager
from app.verification.models import DetectionContext, PluginResult
from app.verification.plugin import VerificationPlugin
from app.verification.plugins.geographic import (
    GeographicOccurrence,
    GeographicPlugin,
)
from app.verification.plugins.audio_quality import AudioQualityPlugin
from app.verification.plugins.seasonal import SeasonalPattern, SeasonalPlugin
from app.verification.repository import save_verification
from app.verification.reviews import ReviewInput, record_review
from app.verification.rules import RuleConfig, RuleEngine


class FixedPlugin(VerificationPlugin):
    name = "fixed"

    def __init__(self, result: PluginResult) -> None:
        self.result = result

    def verify(self, context: DetectionContext) -> PluginResult:
        del context
        return self.result


def context(
    confidence: float,
    *,
    species: str = "Black-capped Chickadee",
    month: int = 5,
    hour: int = 7,
) -> DetectionContext:
    return DetectionContext(
        detection_id=1,
        recording_id=1,
        station_id="test-station",
        scientific_name=None,
        common_name=species,
        birdnet_confidence=confidence,
        recorded_at=datetime(2026, month, 1, hour, tzinfo=timezone.utc),
        audio_path=Path("test.wav"),
    )


class RuleEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = RuleEngine(RuleConfig(0.40, 0.95))

    def test_low_confidence_rejects_without_plugins(self) -> None:
        plugin = FixedPlugin(
            PluginResult("fixed", "support", 0.99, 2.0, "Should not run")
        )
        decision = VerificationManager([plugin], rules=self.engine).verify(
            context(0.39)
        )
        self.assertEqual("rejected", decision.status)
        self.assertEqual((), decision.plugin_results)

    def test_high_confidence_auto_accepts(self) -> None:
        decision = VerificationManager([], rules=self.engine).verify(
            context(0.97)
        )
        self.assertEqual("verified", decision.status)
        self.assertAlmostEqual(0.97, decision.score)


class ConsensusTests(unittest.TestCase):
    def test_independent_support_increases_confidence(self) -> None:
        plugins = [
            FixedPlugin(
                PluginResult("second", "support", 0.88, 1.25, "Model agrees.")
            ),
            FixedPlugin(
                PluginResult("location", "support", 0.90, 0.65, "Common locally.")
            ),
        ]
        decision = VerificationManager(plugins).verify(context(0.84))
        self.assertEqual("verified", decision.status)
        self.assertGreater(decision.score, 0.84)
        self.assertIn("Model agrees.", decision.explanation)
        self.assertEqual("birdnet", decision.evidence[0]["source"])

    def test_conflicting_model_can_prevent_verification(self) -> None:
        plugin = FixedPlugin(
            PluginResult(
                "second", "oppose", 0.95, 1.25, "Second model disagrees."
            )
        )
        decision = VerificationManager([plugin]).verify(context(0.84))
        self.assertIn(decision.status, {"uncertain", "rejected"})
        self.assertLess(decision.score, 0.84)

    def test_poor_audio_reduces_confidence(self) -> None:
        plugin = FixedPlugin(
            PluginResult(
                "audio_quality", "oppose", 0.95, 0.50, "Audio is clipped."
            )
        )
        decision = VerificationManager([plugin]).verify(context(0.75))
        self.assertLess(decision.score, 0.75)


class ContextPluginTests(unittest.TestCase):
    @patch("app.verification.plugins.audio_quality.sf.read")
    @patch("app.verification.plugins.audio_quality.sf.info")
    def test_clipped_audio_is_opposing_evidence(self, info, read) -> None:
        info.return_value.samplerate = 48000
        info.return_value.frames = 1000
        read.return_value = (np.ones(1000), 48000)
        result = AudioQualityPlugin().verify(context(0.80))
        self.assertEqual("oppose", result.verdict)
        self.assertGreater(result.details["clipping_fraction"], 0.01)

    def test_rare_species_is_opposing_evidence(self) -> None:
        plugin = GeographicPlugin(
            {"Snow Goose": GeographicOccurrence("rare", 0.85)},
            region_name="Test Region",
        )
        result = plugin.verify(context(0.80, species="Snow Goose"))
        self.assertEqual("oppose", result.verdict)

    def test_rare_species_increases_review_priority(self) -> None:
        plugin = GeographicPlugin(
            {"Snow Goose": GeographicOccurrence("rare", 0.85)},
            region_name="Test Region",
        )
        decision = VerificationManager([plugin]).verify(
            context(0.80, species="Snow Goose")
        )
        self.assertIn("regional_rare", decision.review_flags)
        self.assertGreater(decision.review_priority, 0)

    def test_migration_species_is_supported_in_expected_month(self) -> None:
        plugin = SeasonalPlugin(
            {
                "Swainson's Thrush": SeasonalPattern(
                    frozenset({4, 5, 6, 7, 8, 9})
                )
            }
        )
        result = plugin.verify(
            context(0.80, species="Swainson's Thrush", month=5)
        )
        self.assertEqual("support", result.verdict)

    def test_out_of_season_species_is_opposing_evidence(self) -> None:
        plugin = SeasonalPlugin(
            {"Snow Goose": SeasonalPattern(frozenset({10, 11, 12, 1, 2, 3}))}
        )
        result = plugin.verify(context(0.80, species="Snow Goose", month=7))
        self.assertEqual("oppose", result.verdict)
        self.assertFalse(result.details["month_expected"])

    def test_nocturnal_detection_at_noon_has_minor_penalty(self) -> None:
        plugin = SeasonalPlugin(
            {
                "Great Horned Owl": SeasonalPattern(
                    frozenset(range(1, 13)), (18, 7)
                )
            }
        )
        result = plugin.verify(
            context(0.80, species="Great Horned Owl", hour=12)
        )
        self.assertEqual("oppose", result.verdict)
        self.assertLess(result.weight, 0.55)


class PersistenceTests(unittest.TestCase):
    def test_migration_and_plugin_outputs_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            connection = sqlite3.connect(":memory:")
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(
                """
                CREATE TABLE stations (
                    id TEXT PRIMARY KEY, name TEXT, timezone TEXT, created_at TEXT
                );
                CREATE TABLE recordings (
                    id INTEGER PRIMARY KEY, station_id TEXT, file_path TEXT,
                    recorded_at TEXT, duration_seconds INTEGER,
                    sample_rate INTEGER, channels INTEGER, sample_format TEXT,
                    file_size_bytes INTEGER, processing_status TEXT,
                    created_at TEXT,
                    FOREIGN KEY (station_id) REFERENCES stations(id)
                );
                """
            )
            apply_migrations(
                connection,
                Path(__file__).parents[1] / "data" / "database" / "migrations",
            )
            connection.execute(
                "INSERT INTO stations VALUES ('s', 'S', 'UTC', 'now')"
            )
            connection.execute(
                """
                INSERT INTO recordings VALUES
                (1, 's', ?, '2026-05-01T07:00:00+00:00', 60, 48000, 1,
                 'S16_LE', 1, 'processed', 'now')
                """,
                (str(Path(directory) / "clip.wav"),),
            )
            cursor = connection.execute(
                """
                INSERT INTO detections (
                    recording_id, detector, scientific_name, common_name,
                    confidence, start_time, end_time
                ) VALUES (1, 'birdnet', NULL, 'Test Bird', .8, 0, 3)
                """
            )
            decision = ConsensusEngine().decide(
                context(0.80),
                [PluginResult("fixed", "support", 0.8, 0.5, "Supports.")],
                RuleEngine().evaluate(context(0.80)),
            )
            save_verification(connection, int(cursor.lastrowid), decision)
            verification = connection.execute(
                "SELECT * FROM verifications"
            ).fetchone()
            output = connection.execute(
                "SELECT * FROM verification_results"
            ).fetchone()
            self.assertIsNotNone(verification)
            self.assertEqual("fixed", output["plugin_name"])
            self.assertEqual("unreviewed", verification["review_status"])
            review_id = record_review(
                connection,
                ReviewInput(
                    int(cursor.lastrowid),
                    "corrected_species",
                    "field-reviewer",
                    notes="Call belongs to another species.",
                    corrected_common_name="Correct Bird",
                    confidence_after=0.99,
                ),
            )
            review = connection.execute(
                "SELECT * FROM latest_detection_reviews"
            ).fetchone()
            self.assertGreater(review_id, 0)
            self.assertEqual("Test Bird", review["original_common_name"])
            self.assertEqual("Correct Bird", review["corrected_common_name"])
            self.assertEqual("corrected_species", review["review_state"])
            connection.close()


if __name__ == "__main__":
    unittest.main()
