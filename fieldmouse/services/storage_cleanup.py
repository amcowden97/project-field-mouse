from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


DEFAULT_DATABASE = Path("data/database/fieldmouse.db")
DEFAULT_EMPTY_RETENTION_DAYS = 3
DEFAULT_DETECTION_RETENTION_DAYS = 30


def table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    rows = connection.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {str(row["name"]) for row in rows}


def choose_column(
    available: set[str],
    candidates: tuple[str, ...],
) -> str | None:
    for candidate in candidates:
        if candidate in available:
            return candidate

    return None


def parse_timestamp(value: object) -> datetime | None:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    normalized = text.replace("Z", "+00:00")

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def resolve_audio_path(raw_path: object) -> Path:
    path = Path(str(raw_path)).expanduser()

    if path.is_absolute():
        return path

    return Path.cwd() / path


def format_bytes(value: int) -> str:
    size = float(value)

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"

        size /= 1024

    return f"{size:.1f} TB"


def get_candidates(
    connection: sqlite3.Connection,
    *,
    empty_cutoff: datetime,
    detection_cutoff: datetime,
) -> list[sqlite3.Row]:
    columns = table_columns(
        connection,
        "recordings",
    )

    path_column = choose_column(
        columns,
        (
            "file_path",
            "path",
            "audio_path",
            "recording_path",
            "filename",
        ),
    )

    timestamp_column = choose_column(
        columns,
        (
            "recorded_at",
            "started_at",
            "created_at",
            "timestamp",
        ),
    )

    status_column = choose_column(
        columns,
        (
            "processing_status",
            "status",
        ),
    )

    if path_column is None:
        raise RuntimeError(
            "Could not find the recording audio path column."
        )

    if timestamp_column is None:
        raise RuntimeError(
            "Could not find the recording timestamp column."
        )

    status_selection = (
        f"r.{status_column} AS processing_status"
        if status_column
        else "'unknown' AS processing_status"
    )

    rows = connection.execute(
        f"""
        SELECT
            r.id,
            r.{path_column} AS audio_path,
            r.{timestamp_column} AS recorded_at,
            {status_selection},
            COUNT(d.id) AS detection_count
        FROM recordings AS r
        LEFT JOIN detections AS d
            ON d.recording_id = r.id
        GROUP BY
            r.id,
            r.{path_column},
            r.{timestamp_column}
        ORDER BY r.id
        """
    ).fetchall()

    candidates: list[sqlite3.Row] = []

    for row in rows:
        status = str(
            row["processing_status"] or ""
        ).lower()

        if status in {
            "pending",
            "processing",
            "recording",
            "in_progress",
        }:
            continue

        recorded_at = parse_timestamp(
            row["recorded_at"]
        )

        if recorded_at is None:
            continue

        detection_count = int(
            row["detection_count"]
        )

        cutoff = (
            detection_cutoff
            if detection_count > 0
            else empty_cutoff
        )

        if recorded_at < cutoff:
            candidates.append(row)

    return candidates


def delete_recording(
    connection: sqlite3.Connection,
    *,
    recording_id: int,
    audio_path: Path,
) -> tuple[bool, int]:
    deleted_file = False
    freed_bytes = 0

    if audio_path.exists():
        try:
            freed_bytes = audio_path.stat().st_size
            audio_path.unlink()
            deleted_file = True
        except OSError as error:
            raise RuntimeError(
                f"Could not delete {audio_path}: {error}"
            ) from error

    connection.execute(
        """
        DELETE FROM detections
        WHERE recording_id = ?
        """,
        (recording_id,),
    )

    connection.execute(
        """
        DELETE FROM recordings
        WHERE id = ?
        """,
        (recording_id,),
    )

    return deleted_file, freed_bytes


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Remove old Project Field Mouse recordings "
            "according to retention rules."
        )
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
    )

    parser.add_argument(
        "--empty-retention-days",
        type=int,
        default=DEFAULT_EMPTY_RETENTION_DAYS,
        help=(
            "Days to keep recordings with no detections."
        ),
    )

    parser.add_argument(
        "--detection-retention-days",
        type=int,
        default=DEFAULT_DETECTION_RETENTION_DAYS,
        help=(
            "Days to keep recordings containing detections."
        ),
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Actually delete files and database rows. "
            "Without this option, cleanup is a dry run."
        ),
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    if arguments.empty_retention_days < 0:
        raise ValueError(
            "Empty retention days cannot be negative."
        )

    if arguments.detection_retention_days < 0:
        raise ValueError(
            "Detection retention days cannot be negative."
        )

    if not arguments.database.exists():
        raise FileNotFoundError(
            f"Database not found: {arguments.database}"
        )

    now = datetime.now(timezone.utc)

    empty_cutoff = now - timedelta(
        days=arguments.empty_retention_days
    )

    detection_cutoff = now - timedelta(
        days=arguments.detection_retention_days
    )

    connection = sqlite3.connect(
        arguments.database
    )
    connection.row_factory = sqlite3.Row

    try:
        candidates = get_candidates(
            connection,
            empty_cutoff=empty_cutoff,
            detection_cutoff=detection_cutoff,
        )

        mode = "APPLY" if arguments.apply else "DRY RUN"

        print("Project Field Mouse storage cleanup")
        print(f"Mode: {mode}")
        print(
            "No-detection retention: "
            f"{arguments.empty_retention_days} day(s)"
        )
        print(
            "Detection retention: "
            f"{arguments.detection_retention_days} day(s)"
        )
        print()

        if not candidates:
            print("No recordings are eligible for cleanup.")
            return 0

        total_bytes = 0
        deleted_rows = 0
        deleted_files = 0

        for row in candidates:
            recording_id = int(row["id"])
            detection_count = int(
                row["detection_count"]
            )
            audio_path = resolve_audio_path(
                row["audio_path"]
            )

            file_size = (
                audio_path.stat().st_size
                if audio_path.exists()
                else 0
            )

            total_bytes += file_size

            print(
                f"Recording {recording_id}: "
                f"{row['recorded_at']} | "
                f"detections={detection_count} | "
                f"{format_bytes(file_size)} | "
                f"{audio_path}"
            )

            if arguments.apply:
                (
                    file_deleted,
                    freed_bytes,
                ) = delete_recording(
                    connection,
                    recording_id=recording_id,
                    audio_path=audio_path,
                )

                deleted_rows += 1

                if file_deleted:
                    deleted_files += 1

                if freed_bytes != file_size:
                    total_bytes += (
                        freed_bytes - file_size
                    )

        print()
        print(
            f"Eligible recordings: {len(candidates)}"
        )
        print(
            f"Potential storage reclaimed: "
            f"{format_bytes(total_bytes)}"
        )

        if arguments.apply:
            connection.commit()

            print(
                f"Deleted database rows: "
                f"{deleted_rows}"
            )
            print(
                f"Deleted audio files: "
                f"{deleted_files}"
            )
            print("Cleanup complete.")
        else:
            connection.rollback()

            print()
            print(
                "Nothing was deleted. Run again with "
                "--apply to perform this cleanup."
            )

        return 0
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
