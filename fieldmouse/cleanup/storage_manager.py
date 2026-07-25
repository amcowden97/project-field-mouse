from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = PROJECT_ROOT / "data" / "database" / "fieldmouse.db"
RECORDINGS_ROOT = (PROJECT_ROOT / "data" / "recordings").resolve()


@dataclass
class CleanupCandidate:
    recording_id: int
    file_path: str
    recorded_at: str
    file_size_bytes: int


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Delete processed Project Field Mouse recordings that have no "
            "detections and are older than the configured retention period."
        )
    )

    parser.add_argument(
        "--retention-hours",
        type=int,
        default=24,
        help="Keep recordings newer than this many hours. Default: 24",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete files. Without this option, only show a dry run.",
    )

    return parser.parse_args()


def connect_database() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def find_candidates(
    connection: sqlite3.Connection,
    cutoff: datetime,
) -> list[CleanupCandidate]:
    rows = connection.execute(
        """
        SELECT
            r.id,
            r.file_path,
            r.recorded_at,
            COALESCE(r.file_size_bytes, 0) AS file_size_bytes
        FROM recordings r
        WHERE r.processing_status = 'processed'
          AND datetime(r.recorded_at) < datetime(?)
          AND NOT EXISTS (
              SELECT 1
              FROM detections d
              WHERE d.recording_id = r.id
          )
        ORDER BY r.recorded_at ASC
        """,
        (cutoff.isoformat(),),
    ).fetchall()

    return [
        CleanupCandidate(
            recording_id=row["id"],
            file_path=row["file_path"],
            recorded_at=row["recorded_at"],
            file_size_bytes=row["file_size_bytes"],
        )
        for row in rows
    ]


def resolve_recording_path(file_path: str) -> Path:
    path = (PROJECT_ROOT / file_path).resolve()

    if path != RECORDINGS_ROOT and RECORDINGS_ROOT not in path.parents:
        raise ValueError(f"Refusing unsafe path outside recordings directory: {path}")

    return path


def format_size(byte_count: int) -> str:
    size = float(byte_count)

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.2f} {unit}"

        size /= 1024

    return f"{byte_count} B"


def remove_empty_parent_directories(path: Path) -> None:
    current = path.parent

    while current != RECORDINGS_ROOT:
        try:
            current.rmdir()
        except OSError:
            break

        current = current.parent


def perform_cleanup(
    connection: sqlite3.Connection,
    candidates: list[CleanupCandidate],
) -> tuple[int, int, int]:
    deleted_files = 0
    missing_files = 0
    reclaimed_bytes = 0

    for candidate in candidates:
        try:
            audio_path = resolve_recording_path(candidate.file_path)
        except ValueError as error:
            print(f"SKIPPED: {error}")
            continue

        try:
            if audio_path.is_file():
                actual_size = audio_path.stat().st_size
                audio_path.unlink()

                deleted_files += 1
                reclaimed_bytes += actual_size

                remove_empty_parent_directories(audio_path)
            else:
                missing_files += 1

            connection.execute(
                """
                DELETE FROM recordings
                WHERE id = ?
                  AND NOT EXISTS (
                      SELECT 1
                      FROM detections
                      WHERE recording_id = recordings.id
                  )
                """,
                (candidate.recording_id,),
            )

            connection.commit()

        except OSError as error:
            connection.rollback()
            print(f"FAILED: {audio_path}: {error}")

    return deleted_files, missing_files, reclaimed_bytes


def main() -> None:
    arguments = parse_arguments()

    if arguments.retention_hours < 1:
        raise SystemExit("--retention-hours must be at least 1")

    cutoff = datetime.now(timezone.utc) - timedelta(
        hours=arguments.retention_hours
    )

    print("Project Field Mouse Storage Manager")
    print("-----------------------------------")
    print(f"Database:          {DATABASE_PATH}")
    print(f"Recordings root:   {RECORDINGS_ROOT}")
    print(f"Retention period:  {arguments.retention_hours} hours")
    print(f"Delete before:     {cutoff.isoformat()}")
    print(f"Mode:              {'APPLY' if arguments.apply else 'DRY RUN'}")
    print()

    if not DATABASE_PATH.is_file():
        raise SystemExit(f"Database not found: {DATABASE_PATH}")

    with connect_database() as connection:
        candidates = find_candidates(connection, cutoff)

        estimated_bytes = sum(
            candidate.file_size_bytes for candidate in candidates
        )

        print(f"Cleanup candidates: {len(candidates)}")
        print(f"Estimated reclaim:  {format_size(estimated_bytes)}")

        if candidates:
            print()
            print("Oldest candidates:")

            for candidate in candidates[:10]:
                print(
                    f"  {candidate.recorded_at}  "
                    f"{format_size(candidate.file_size_bytes):>10}  "
                    f"{candidate.file_path}"
                )

        if not arguments.apply:
            print()
            print("Dry run only. No files or database rows were deleted.")
            print("Run again with --apply after reviewing the results.")
            return

        print()
        print("Applying cleanup...")

        deleted_files, missing_files, reclaimed_bytes = perform_cleanup(
            connection,
            candidates,
        )

        print()
        print("Cleanup complete")
        print("----------------")
        print(f"Deleted files:     {deleted_files}")
        print(f"Missing files:     {missing_files}")
        print(f"Space reclaimed:   {format_size(reclaimed_bytes)}")


if __name__ == "__main__":
    main()
