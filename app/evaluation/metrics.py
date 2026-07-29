from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import math
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
    per_species: dict[str, dict[str, float | int]]

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
    evaluated = 0
    matrix: Counter[tuple[str, str]] = Counter()
    for record in records:
        if record.get("review", {}).get("state") not in {
            "verified",
            "corrected_species",
            "rejected",
        }:
            continue
        evaluated += 1
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
    species_metrics: dict[str, dict[str, float | int]] = {}
    for species in (label for label in labels if label != "__absent__"):
        species_tp = matrix[(species, species)]
        species_fp = sum(
            matrix[(actual, species)]
            for actual in labels
            if actual != species
        )
        species_fn = sum(
            matrix[(species, predicted)]
            for predicted in labels
            if predicted != species
        )
        species_metrics[species] = {
            "support": sum(matrix[(species, predicted)] for predicted in labels),
            "precision": _ratio(species_tp, species_tp + species_fp),
            "recall": _ratio(species_tp, species_tp + species_fn),
            "f1": _ratio(
                2 * species_tp,
                2 * species_tp + species_fp + species_fn,
            ),
        }
    return Metrics(
        samples=evaluated,
        available_predictions=available,
        true_positive=tp,
        true_negative=tn,
        false_positive=fp,
        false_negative=fn,
        precision=_ratio(tp, tp + fp),
        recall=_ratio(tp, tp + fn),
        false_positive_rate=_ratio(fp, fp + tn),
        false_negative_rate=_ratio(fn, fn + tp),
        accuracy=_ratio(tp + tn, evaluated),
        f1=_ratio(2 * tp, 2 * tp + fp + fn),
        confusion_matrix=confusion,
        per_species=species_metrics,
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


def evidence_source_ablation(
    records: list[dict[str, Any]],
    *,
    threshold: float,
) -> dict[str, dict[str, float]]:
    sources = sorted(
        {
            item["source"]
            for record in records
            for item in record.get("verification_evidence", [])
            if item.get("source") != "birdnet"
        }
    )

    def evidence_score(
        record: dict[str, Any], excluded: str | None = None
    ) -> float:
        total = 0.0
        for item in record.get("verification_evidence", []):
            if item.get("source") == excluded:
                continue
            score = min(max(float(item.get("score", 0.5)), 0.01), 0.99)
            strength = abs(math.log(score / (1.0 - score)))
            direction = {
                "support": 1.0,
                "neutral": 0.0,
                "oppose": -1.0,
            }.get(item.get("outcome"), 0.0)
            total += direction * float(item.get("weight", 1.0)) * strength
        return 1.0 / (1.0 + math.exp(-max(min(total, 30.0), -30.0)))

    def scored(excluded: str | None) -> list[dict[str, Any]]:
        output = []
        for record in records:
            clone = dict(record)
            clone["predictions"] = dict(record.get("predictions", {}))
            species = clone["predictions"].get("verification", {}).get(
                "species"
            )
            clone["predictions"]["ablation"] = {
                "species": species,
                "score": evidence_score(record, excluded),
            }
            output.append(clone)
        return output

    baseline = evaluate_predictions(
        scored(None), "ablation", threshold=threshold
    )
    return {
        source: {
            "baseline_f1": baseline.f1,
            "without_source_f1": (
                without := evaluate_predictions(
                    scored(source), "ablation", threshold=threshold
                )
            ).f1,
            "f1_contribution": baseline.f1 - without.f1,
        }
        for source in sources
    }
