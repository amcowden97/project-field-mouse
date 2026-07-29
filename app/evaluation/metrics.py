from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Metrics:
    samples: int
    available_predictions: int
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float
    false_positive_rate: float
    false_negative_rate: float
    accuracy: float
    f1: float
    confusion_matrix: dict[str, dict[str, int]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def evaluate_predictions(
    records: list[dict[str, Any]],
    system: str,
    *,
    threshold: float,
) -> Metrics:
    tp = tn = fp = fn = 0
    available = 0
    matrix: Counter[tuple[str, str]] = Counter()
    for record in records:
        truth = record["truth"]
        prediction = record.get("predictions", {}).get(system) or {}
        score = prediction.get("score")
        available += score is not None
        predicted_present = score is not None and float(score) >= threshold
        actual_present = bool(truth.get("present"))
        if actual_present and predicted_present:
            tp += 1
        elif actual_present:
            fn += 1
        elif predicted_present:
            fp += 1
        else:
            tn += 1

        actual_species = truth.get("species") if actual_present else "__absent__"
        predicted_species = (
            prediction.get("species") if predicted_present else "__absent__"
        )
        matrix[(str(actual_species), str(predicted_species))] += 1

    labels = sorted({label for pair in matrix for label in pair})
    confusion = {
        actual: {
            predicted: matrix[(actual, predicted)] for predicted in labels
        }
        for actual in labels
    }
    return Metrics(
        samples=len(records),
        available_predictions=available,
        true_positive=tp,
        true_negative=tn,
        false_positive=fp,
        false_negative=fn,
        precision=_ratio(tp, tp + fp),
        recall=_ratio(tp, tp + fn),
        false_positive_rate=_ratio(fp, fp + tn),
        false_negative_rate=_ratio(fn, fn + tp),
        accuracy=_ratio(tp + tn, len(records)),
        f1=_ratio(2 * tp, 2 * tp + fp + fn),
        confusion_matrix=confusion,
    )


def compare_systems(
    records: list[dict[str, Any]],
    thresholds: dict[str, float],
) -> dict[str, dict[str, Any]]:
    return {
        system: evaluate_predictions(
            records, system, threshold=threshold
        ).to_dict()
        for system, threshold in thresholds.items()
    }
