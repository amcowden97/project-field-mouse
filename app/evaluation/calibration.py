from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class CalibrationResult:
    sources: tuple[str, ...]
    weights: tuple[float, ...]
    intercept: float
    decision_threshold: float
    samples: int
    training_f1: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "method": "projected_logistic_regression",
            "sources": dict(zip(self.sources, self.weights, strict=True)),
            "intercept": self.intercept,
            "decision_threshold": self.decision_threshold,
            "samples": self.samples,
            "training_f1": self.training_f1,
        }


def _logit(score: float) -> float:
    bounded = min(max(score, 0.01), 0.99)
    return math.log(bounded / (1.0 - bounded))


def _feature(evidence: dict[str, Any]) -> float:
    direction = {
        "support": 1.0,
        "neutral": 0.0,
        "oppose": -1.0,
    }.get(evidence.get("outcome"), 0.0)
    return direction * abs(_logit(float(evidence.get("score", 0.5))))


def calibrate(
    records: list[dict[str, Any]],
    *,
    iterations: int = 2000,
    learning_rate: float = 0.05,
    regularization: float = 0.01,
) -> CalibrationResult:
    labeled = [
        record
        for record in records
        if record.get("review", {}).get("state")
        in {"verified", "corrected_species", "rejected"}
    ]
    if len(labeled) < 10:
        raise ValueError("Calibration requires at least 10 reviewed records.")
    sources = sorted(
        {
            evidence["source"]
            for record in labeled
            for evidence in record.get("verification_evidence", [])
        }
    )
    if "birdnet" not in sources:
        sources.insert(0, "birdnet")
    source_index = {source: index for index, source in enumerate(sources)}
    features = np.zeros((len(labeled), len(sources)), dtype=float)
    labels = np.zeros(len(labeled), dtype=float)
    for row_index, record in enumerate(labeled):
        labels[row_index] = float(record["truth"]["present"])
        evidence_items = list(record.get("verification_evidence", []))
        if not any(item.get("source") == "birdnet" for item in evidence_items):
            birdnet = record["predictions"]["birdnet"]
            evidence_items.append(
                {
                    "source": "birdnet",
                    "outcome": "support",
                    "score": birdnet["score"],
                }
            )
        for evidence in evidence_items:
            source = evidence.get("source")
            if source in source_index:
                features[row_index, source_index[source]] = _feature(evidence)

    weights = np.ones(len(sources), dtype=float)
    intercept = 0.0
    for _ in range(iterations):
        logits = features @ weights + intercept
        probabilities = 1.0 / (1.0 + np.exp(-np.clip(logits, -30, 30)))
        residual = probabilities - labels
        gradient = features.T @ residual / len(labels)
        gradient += regularization * weights
        weights = np.maximum(0.0, weights - learning_rate * gradient)
        intercept -= learning_rate * float(np.mean(residual))

    probabilities = 1.0 / (
        1.0 + np.exp(-np.clip(features @ weights + intercept, -30, 30))
    )
    best_threshold = 0.5
    best_f1 = -1.0
    for threshold in np.linspace(0.1, 0.9, 81):
        predicted = probabilities >= threshold
        tp = int(np.sum((predicted == 1) & (labels == 1)))
        fp = int(np.sum((predicted == 1) & (labels == 0)))
        fn = int(np.sum((predicted == 0) & (labels == 1)))
        f1 = (2 * tp / (2 * tp + fp + fn)) if (2 * tp + fp + fn) else 0.0
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = float(threshold)
    return CalibrationResult(
        tuple(sources),
        tuple(float(weight) for weight in weights),
        intercept,
        best_threshold,
        len(labeled),
        best_f1,
    )


def write_calibration(path: Path, result: CalibrationResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
