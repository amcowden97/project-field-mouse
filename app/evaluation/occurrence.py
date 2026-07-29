from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_occurrence_profile(
    input_path: Path,
    *,
    region_id: str,
    region_name: str,
    source_name: str,
    source_version: str,
) -> dict[str, Any]:
    """Build a profile from normalized, licensed checklist-frequency CSV."""
    counts: dict[str, int] = defaultdict(int)
    checklists: dict[str, int] = defaultdict(int)
    months: dict[str, set[int]] = defaultdict(set)
    common_names: dict[str, str] = {}
    with input_path.open(newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            scientific = row["scientific_name"].strip()
            common_names[scientific] = row.get("common_name", "").strip()
            observations = int(row["observation_count"])
            checklist_count = int(row["checklist_count"])
            month = int(row["month"])
            counts[scientific] += observations
            checklists[scientific] += checklist_count
            if observations:
                months[scientific].add(month)

    occurrences: dict[str, dict[str, Any]] = {}
    seasonal: dict[str, dict[str, Any]] = {}
    for scientific in sorted(counts):
        frequency = (
            counts[scientific] / checklists[scientific]
            if checklists[scientific]
            else 0.0
        )
        if frequency >= 0.10:
            status, score = "common", 0.90
        elif frequency >= 0.01:
            status, score = "expected", 0.75
        elif frequency > 0.0:
            status, score = "rare", 0.80
        else:
            status, score = "absent", 0.90
        value = {
            "status": status,
            "score": score,
            "frequency": round(frequency, 6),
            "observations": counts[scientific],
            "checklists": checklists[scientific],
        }
        occurrences[scientific] = value
        if common_names[scientific]:
            occurrences[common_names[scientific]] = value
        pattern = {"expected_months": sorted(months[scientific])}
        seasonal[scientific] = pattern
        if common_names[scientific]:
            seasonal[common_names[scientific]] = pattern

    source_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
    return {
        "schema_version": 1,
        "id": region_id,
        "name": region_name,
        "profile_version": (
            f"{source_version}-{datetime.now(timezone.utc):%Y%m%d}"
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "name": source_name,
            "version": source_version,
            "sha256": source_hash,
            "license_review_required": True,
        },
        "occurrences": occurrences,
        "seasonal_patterns": seasonal,
    }


def write_occurrence_profile(path: Path, profile: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(profile, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
