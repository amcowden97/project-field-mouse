from __future__ import annotations

import argparse
import json
import sqlite3
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path

from app.database.migrations import apply_migrations
from app.evaluation.calibration import calibrate, write_calibration
from app.evaluation.dataset import export_evaluation_dataset
from app.evaluation.metrics import compare_systems, evidence_source_ablation
from app.evaluation.occurrence import (
    build_occurrence_profile,
    write_occurrence_profile,
)
from app.evaluation.performance import profile_callable
from app.evaluation.report import (
    read_jsonl,
    write_benchmark_report,
)
from app.verification.factory import build_verification_manager
from app.verification.models import DetectionContext
from app.verification.reviews import ReviewInput, record_review


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    apply_migrations(connection)
    return connection


def review_command(arguments: argparse.Namespace) -> None:
    with closing(connect(arguments.database)) as connection:
        review_id = record_review(
            connection,
            ReviewInput(
                detection_id=arguments.detection_id,
                state=arguments.state,
                reviewer=arguments.reviewer,
                notes=arguments.notes,
                corrected_scientific_name=arguments.corrected_scientific_name,
                corrected_common_name=arguments.corrected_common_name,
                confidence_after=arguments.confidence_after,
            ),
        )
        connection.commit()
    print(json.dumps({"review_id": review_id}))


def export_command(arguments: argparse.Namespace) -> None:
    with closing(connect(arguments.database)) as connection:
        result = export_evaluation_dataset(
            connection, arguments.output, copy_mode=arguments.copy_mode
        )
    print(json.dumps(result.__dict__, default=str, sort_keys=True))


def benchmark_command(arguments: argparse.Namespace) -> None:
    records = read_jsonl(arguments.dataset)
    thresholds = {
        "birdnet": arguments.birdnet_threshold,
        "verification": arguments.verification_threshold,
        "second_model": arguments.second_model_threshold,
    }
    results = compare_systems(records, thresholds)
    results["evidence_source_ablation"] = evidence_source_ablation(
        records, threshold=arguments.verification_threshold
    )
    write_benchmark_report(
        arguments.output, results, dataset_path=arguments.dataset
    )
    print(json.dumps(results, indent=2, sort_keys=True))


def calibrate_command(arguments: argparse.Namespace) -> None:
    result = calibrate(read_jsonl(arguments.dataset))
    write_calibration(arguments.output, result)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))


def occurrence_command(arguments: argparse.Namespace) -> None:
    profile = build_occurrence_profile(
        arguments.input,
        region_id=arguments.region_id,
        region_name=arguments.region_name,
        source_name=arguments.source_name,
        source_version=arguments.source_version,
    )
    write_occurrence_profile(arguments.output, profile)
    print(json.dumps(profile["source"], indent=2, sort_keys=True))


def profile_command(arguments: argparse.Namespace) -> None:
    connection = connect(arguments.database)
    try:
        row = connection.execute(
            """
            SELECT d.id, d.recording_id, d.scientific_name, d.common_name,
                   d.confidence, d.start_time, d.end_time, r.station_id,
                   r.recorded_at, r.file_path
            FROM detections AS d
            JOIN recordings AS r ON r.id = d.recording_id
            WHERE (? IS NULL OR d.id = ?)
            ORDER BY d.id DESC LIMIT 1
            """,
            (arguments.detection_id, arguments.detection_id),
        ).fetchone()
        if row is None:
            raise SystemExit("No detection is available to profile.")
        started = time.perf_counter()
        manager = build_verification_manager(connection)
        startup = time.perf_counter() - started
        if manager is None:
            raise SystemExit("Verification is disabled.")
        context = DetectionContext(
            int(row["id"]),
            int(row["recording_id"]),
            str(row["station_id"]),
            row["scientific_name"],
            str(row["common_name"]),
            float(row["confidence"]),
            datetime.fromisoformat(
                str(row["recorded_at"]).replace("Z", "+00:00")
            ),
            Path(row["file_path"]).resolve(),
            row["start_time"],
            row["end_time"],
        )
        report = profile_callable(
            lambda: manager.verify(context),
            iterations=arguments.iterations,
            startup_seconds=startup,
        )
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    finally:
        connection.close()


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Verification evaluation tools")
    root.add_argument(
        "--database",
        type=Path,
        default=Path("data/database/fieldmouse.db"),
    )
    commands = root.add_subparsers(required=True)

    review = commands.add_parser("review")
    review.add_argument("detection_id", type=int)
    review.add_argument(
        "state",
        choices=[
            "pending_review",
            "verified",
            "rejected",
            "corrected_species",
            "ignored",
        ],
    )
    review.add_argument("--reviewer", required=True)
    review.add_argument("--notes", default="")
    review.add_argument("--corrected-scientific-name")
    review.add_argument("--corrected-common-name")
    review.add_argument("--confidence-after", type=float)
    review.set_defaults(handler=review_command)

    export = commands.add_parser("export")
    export.add_argument("output", type=Path)
    export.add_argument(
        "--copy-mode", choices=["copy", "hardlink", "manifest"], default="manifest"
    )
    export.set_defaults(handler=export_command)

    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("dataset", type=Path)
    benchmark.add_argument("output", type=Path)
    benchmark.add_argument("--birdnet-threshold", type=float, default=0.70)
    benchmark.add_argument("--verification-threshold", type=float, default=0.90)
    benchmark.add_argument("--second-model-threshold", type=float, default=0.70)
    benchmark.set_defaults(handler=benchmark_command)

    calibration = commands.add_parser("calibrate")
    calibration.add_argument("dataset", type=Path)
    calibration.add_argument("output", type=Path)
    calibration.set_defaults(handler=calibrate_command)

    occurrence = commands.add_parser("build-occurrence")
    occurrence.add_argument("input", type=Path)
    occurrence.add_argument("output", type=Path)
    occurrence.add_argument("--region-id", required=True)
    occurrence.add_argument("--region-name", required=True)
    occurrence.add_argument("--source-name", required=True)
    occurrence.add_argument("--source-version", required=True)
    occurrence.set_defaults(handler=occurrence_command)

    profile = commands.add_parser("profile")
    profile.add_argument("output", type=Path)
    profile.add_argument("--detection-id", type=int)
    profile.add_argument("--iterations", type=int, default=10)
    profile.set_defaults(handler=profile_command)
    return root


def main() -> int:
    arguments = parser().parse_args()
    arguments.handler(arguments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
