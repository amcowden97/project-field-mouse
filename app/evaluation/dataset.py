from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


CopyMode = Literal["copy", "hardlink", "manifest"]


@dataclass(frozen=True)
class ExportSummary:
    records: int
    copied_files: int
    output_path: Path


def _category(review_state: str | None) -> str:
    return {
        "verified": "verified",
        "corrected_species": "verified",
        "rejected": "false_positive",
        "pending_review": "needs_review",
        "ignored": "unknown",
        None: "needs_review",
    }[review_state]


def export_evaluation_dataset(
    connection: sqlite3.Connection,
    output_path: Path,
    *,
    copy_mode: CopyMode = "manifest",
) -> ExportSummary:
    output_path.mkdir(parents=True, exist_ok=True)
    for category in ("verified", "false_positive", "needs_review", "unknown"):
        (output_path / category).mkdir(exist_ok=True)

    rows = connection.execute(
        """
        SELECT d.id AS detection_id, d.recording_id, d.scientific_name,
               d.common_name, d.confidence AS birdnet_confidence,
               d.start_time, d.end_time, r.station_id, r.recorded_at,
               r.file_path, v.consensus_score, v.status AS verification_status,
               v.evidence_json, v.review_priority, v.review_flags_json,
               review.review_state, review.reviewed_at, review.reviewer,
               review.corrected_scientific_name, review.corrected_common_name,
               review.notes, review.confidence_after
        FROM detections AS d
        JOIN recordings AS r ON r.id = d.recording_id
        LEFT JOIN verifications AS v ON v.detection_id = d.id
        LEFT JOIN latest_detection_reviews AS review
               ON review.detection_id = d.id
        ORDER BY d.id
        """
    ).fetchall()
    manifest_path = output_path / "metadata.jsonl"
    copied = 0
    with manifest_path.open("w", encoding="utf-8") as manifest:
        for row in rows:
            state = row["review_state"]
            category = _category(state)
            source = Path(row["file_path"]).resolve()
            relative_audio: str | None = None
            if copy_mode != "manifest" and source.exists():
                target = output_path / category / (
                    f"detection-{row['detection_id']}-{source.name}"
                )
                if not target.exists():
                    if copy_mode == "copy":
                        shutil.copy2(source, target)
                    else:
                        target.hardlink_to(source)
                    copied += 1
                relative_audio = target.relative_to(output_path).as_posix()
            truth_species = (
                row["corrected_scientific_name"]
                or row["corrected_common_name"]
                or row["scientific_name"]
                or row["common_name"]
                if state in {"verified", "corrected_species"}
                else None
            )
            evidence = json.loads(row["evidence_json"] or "[]")
            second_evidence = next(
                (
                    item
                    for item in evidence
                    if item.get("source") == "second_model"
                ),
                None,
            )
            record = {
                "schema_version": 1,
                "detection_id": row["detection_id"],
                "recording_id": row["recording_id"],
                "audio": relative_audio,
                "source_audio": str(source),
                "clip": {
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                },
                "station_id": row["station_id"],
                "recorded_at": row["recorded_at"],
                "category": category,
                "review": {
                    "state": state or "pending_review",
                    "reviewed_at": row["reviewed_at"],
                    "reviewer": row["reviewer"],
                    "notes": row["notes"],
                    "confidence_after": row["confidence_after"],
                },
                "truth": {
                    "present": state in {"verified", "corrected_species"},
                    "species": truth_species,
                },
                "predictions": {
                    "birdnet": {
                        "species": row["scientific_name"] or row["common_name"],
                        "score": row["birdnet_confidence"],
                    },
                    "verification": {
                        "species": row["scientific_name"] or row["common_name"],
                        "score": row["consensus_score"],
                        "status": row["verification_status"],
                    },
                    "second_model": (
                        {
                            "species": second_evidence["details"].get(
                                "scientific_name"
                            )
                            or second_evidence["details"].get("common_name"),
                            "score": second_evidence.get("score"),
                        }
                        if second_evidence
                        else None
                    ),
                },
                "verification_evidence": evidence,
                "review_priority": row["review_priority"] or 0,
                "review_flags": json.loads(row["review_flags_json"] or "[]"),
            }
            manifest.write(json.dumps(record, sort_keys=True) + "\n")
    return ExportSummary(len(rows), copied, output_path)
