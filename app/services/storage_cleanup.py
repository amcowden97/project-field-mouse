from __future__ import annotations

import argparse
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import load_config


def table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    rows = connection.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {
        str(row["name"] if isinstance(row, sqlite3.Row) else row[1])
        for row in rows
    }


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone() is not None


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
    rare_species: frozenset[str] = frozenset(),
    limit: int | None = None,
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

    excluded_statuses = (
        "pending", "processing", "recording", "in_progress", "audio_expired"
    )
    status_placeholders = ",".join("?" * len(excluded_statuses))
    status_filter = (
        f"AND LOWER(COALESCE(r.{status_column}, '')) "
        f"NOT IN ({status_placeholders})"
        if status_column
        else ""
    )
    limit_clause = "LIMIT ?" if limit is not None else ""
    protection_filter = (
        """
        AND NOT EXISTS (
            SELECT 1 FROM recording_protections AS protection
            WHERE protection.recording_id = r.id
              AND protection.released_at IS NULL
        )
        """
        if table_exists(connection, "recording_protections")
        else ""
    )
    common_parameters: list[object] = (
        list(excluded_statuses) if status_column else []
    )
    empty_parameters: list[object] = [empty_cutoff.isoformat(), *common_parameters]
    if limit is not None:
        empty_parameters.append(limit)
    candidates = connection.execute(
        f"""
        SELECT r.id, r.{path_column} AS audio_path,
               r.{timestamp_column} AS recorded_at, {status_selection},
               0 AS detection_count, NULL AS detected_species
        FROM recordings AS r
        WHERE datetime(r.{timestamp_column}) < datetime(?)
          {status_filter}
          {protection_filter}
          AND NOT EXISTS (
              SELECT 1 FROM detections AS d WHERE d.recording_id = r.id
          )
        ORDER BY r.id
        {limit_clause}
        """,
        empty_parameters,
    ).fetchall()

    # Fail closed for detection-bearing audio until an authoritative rare-species
    # list exists. Empty recordings remain safely recoverable under ENOSPC.
    if not rare_species or (limit is not None and len(candidates) >= limit):
        return list(candidates)

    remaining = None if limit is None else limit - len(candidates)
    rare_names = sorted(rare_species)
    rare_placeholders = ",".join("?" * len(rare_names))
    detected_parameters: list[object] = [
        detection_cutoff.isoformat(),
        *common_parameters,
        *rare_names,
    ]
    if remaining is not None:
        detected_parameters.append(remaining)
    detected = connection.execute(
        f"""
        SELECT r.id, r.{path_column} AS audio_path,
               r.{timestamp_column} AS recorded_at, {status_selection},
               (SELECT COUNT(*) FROM detections AS d
                WHERE d.recording_id = r.id) AS detection_count,
               (SELECT GROUP_CONCAT(DISTINCT d.common_name) FROM detections AS d
                WHERE d.recording_id = r.id) AS detected_species
        FROM recordings AS r
        WHERE datetime(r.{timestamp_column}) < datetime(?)
          {status_filter}
          {protection_filter}
          AND EXISTS (SELECT 1 FROM detections AS d WHERE d.recording_id = r.id)
          AND NOT EXISTS (
              SELECT 1 FROM detections AS d
              WHERE d.recording_id = r.id
                AND LOWER(d.common_name) IN ({rare_placeholders})
          )
        ORDER BY r.id
        {limit_clause}
        """,
        detected_parameters,
    ).fetchall()
    return [*candidates, *detected]


def expire_recording_audio(
    connection: sqlite3.Connection,
    *,
    recording_id: int,
    audio_path: Path,
) -> tuple[bool, int]:
    deleted_file = False
    freed_bytes = 0
    lifecycle_enabled = "source_availability" in table_columns(connection, "recordings")
    if lifecycle_enabled:
        from app.science.recordings import is_recording_protected

        if is_recording_protected(connection, recording_id):
            raise RuntimeError("Active recording protection blocks expiration")

    if audio_path.exists():
        try:
            freed_bytes = audio_path.stat().st_size
            audio_path.unlink()
            deleted_file = True
        except OSError as error:
            raise RuntimeError(
                f"Could not delete {audio_path}: {error}"
            ) from error

    if lifecycle_enabled:
        from app.science.recordings import SourceAvailability, set_source_availability

        set_source_availability(
            connection,
            recording_id=recording_id,
            availability=SourceAvailability.INTENTIONALLY_EXPIRED,
            reason_code="RETENTION_POLICY_EXPIRATION",
            authorized_by="STORAGE_CLEANUP",
            authorization_reference=str(audio_path),
            operation_id=f"storage-cleanup-{recording_id}-{uuid.uuid4()}",
        )
    connection.execute(
        "UPDATE recordings SET processing_status = 'audio_expired' WHERE id = ?",
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
        "--config",
        type=Path,
        default=None,
        help="Station TOML path (defaults to PFM_CONFIG or config/station.toml).",
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=None,
    )

    parser.add_argument(
        "--empty-retention-days",
        type=int,
        default=None,
        help=(
            "Days to keep recordings with no detections."
        ),
    )

    parser.add_argument(
        "--detection-retention-days",
        type=int,
        default=None,
        help=(
            "Days to keep recordings containing detections."
        ),
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Actually expire eligible audio files while preserving "
            "database history. "
            "Without this option, cleanup is a dry run."
        ),
    )
    parser.add_argument(
        "--rare-species",
        action="append",
        default=[],
        help=(
            "Common name to preserve forever. Repeat for each rare species."
        ),
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    config = load_config(arguments.config)
    arguments.database = arguments.database or config.storage.database_path
    arguments.empty_retention_days = (
        arguments.empty_retention_days
        if arguments.empty_retention_days is not None
        else config.storage.empty_recording_retention_days
    )
    arguments.detection_retention_days = (
        arguments.detection_retention_days
        if arguments.detection_retention_days is not None
        else config.storage.detection_recording_retention_days
    )
    rare_species = [
        *config.storage.rare_species,
        *arguments.rare_species,
    ]

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
            rare_species=frozenset(
                name.strip().casefold()
                for name in rare_species
                if name.strip()
            ),
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
        print(
            "Rare species preserved forever: "
            f"{len(set(name.casefold() for name in rare_species))}"
        )
        if not rare_species:
            print(
                "Detection cleanup: disabled (no authoritative "
                "rare-species list configured)"
            )
        print()

        if not candidates:
            print("No recordings are eligible for cleanup.")
            return 0

        total_bytes = 0
        preserved_rows = 0
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
                ) = expire_recording_audio(
                    connection,
                    recording_id=recording_id,
                    audio_path=audio_path,
                )

                preserved_rows += 1

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
                f"Preserved database rows: "
                f"{preserved_rows}"
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
