from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from app.evaluation.calibration import calibrate
from app.evaluation.metrics import evaluate_predictions
from app.evaluation.occurrence import build_occurrence_profile


def record(
    *,
    present: bool,
    birdnet_score: float,
    verification_score: float,
) -> dict:
    state = "verified" if present else "rejected"
    return {
        "review": {"state": state},
        "truth": {
            "present": present,
            "species": "Test Bird" if present else None,
        },
        "predictions": {
            "birdnet": {"species": "Test Bird", "score": birdnet_score},
            "verification": {
                "species": "Test Bird",
                "score": verification_score,
            },
        },
        "verification_evidence": [
            {
                "source": "birdnet",
                "outcome": "support",
                "score": birdnet_score,
            },
            {
                "source": "geographic",
                "outcome": "support" if present else "oppose",
                "score": 0.85,
            },
        ],
    }


class MetricTests(unittest.TestCase):
    def test_metrics_count_false_positives_and_false_negatives(self) -> None:
        records = [
            record(present=True, birdnet_score=0.9, verification_score=0.95),
            record(present=True, birdnet_score=0.4, verification_score=0.3),
            record(present=False, birdnet_score=0.9, verification_score=0.2),
            record(present=False, birdnet_score=0.2, verification_score=0.1),
        ]
        metrics = evaluate_predictions(records, "birdnet", threshold=0.7)
        self.assertEqual(1, metrics.true_positive)
        self.assertEqual(1, metrics.true_negative)
        self.assertEqual(1, metrics.false_positive)
        self.assertEqual(1, metrics.false_negative)
        self.assertEqual(0.5, metrics.f1)

    def test_calibration_is_data_driven(self) -> None:
        records = [
            record(
                present=index % 2 == 0,
                birdnet_score=0.8,
                verification_score=0.9 if index % 2 == 0 else 0.2,
            )
            for index in range(12)
        ]
        result = calibrate(records, iterations=50)
        self.assertEqual(12, result.samples)
        self.assertIn("geographic", result.sources)
        self.assertGreaterEqual(result.training_f1, 0.5)


class OccurrenceProfileTests(unittest.TestCase):
    def test_profile_has_version_provenance_and_seasons(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "occurrence.csv"
            with source.open("w", newline="", encoding="utf-8") as output:
                writer = csv.DictWriter(
                    output,
                    fieldnames=[
                        "scientific_name",
                        "common_name",
                        "month",
                        "observation_count",
                        "checklist_count",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "scientific_name": "Avis testus",
                        "common_name": "Test Bird",
                        "month": 5,
                        "observation_count": 20,
                        "checklist_count": 100,
                    }
                )
            profile = build_occurrence_profile(
                source,
                region_id="test-region",
                region_name="Test Region",
                source_name="Licensed test data",
                source_version="2026",
            )
            self.assertEqual(
                "common", profile["occurrences"]["Avis testus"]["status"]
            )
            self.assertEqual(
                [5],
                profile["seasonal_patterns"]["Avis testus"][
                    "expected_months"
                ],
            )
            self.assertEqual(64, len(profile["source"]["sha256"]))
            json.dumps(profile)


if __name__ == "__main__":
    unittest.main()
