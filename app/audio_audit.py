"""Read-only reconciliation of WAV files and recording database rows."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.config import load_config

CATEGORIES = (
    "Duplicate recordings",
    "Legacy recordings",
    "Missing DB rows",
    "Ingestion failures",
    "Unknown",
)


def parse_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def timestamp_from_filename(path: Path) -> datetime | None:
    stem = path.stem
    formats = (
        "%Y-%m-%dT%H-%M-%S%z",
        "%Y-%m-%dT%H-%M-%S",
    )
    for format_string in formats:
        try:
            parsed = datetime.strptime(stem, format_string)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_path(
    path: Path,
    recordings_root: Path,
    project_root: Path,
) -> str:
    path = path.expanduser()
    if not path.is_absolute():
        project_relative = project_root / path
        recordings_relative = recordings_root / path
        path = (
            project_relative
            if project_relative.exists()
            or path.parts[:2] == ("data", "recordings")
            else recordings_relative
        )
    return str(path.resolve(strict=False))


def read_rows(database: Path, recordings_root: Path) -> list[dict[str, Any]]:
    uri = f"{database.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT
                r.id, r.file_path, r.recorded_at, r.created_at,
                r.processing_status, r.file_size_bytes,
                COUNT(d.id) AS detection_count
            FROM recordings AS r
            LEFT JOIN detections AS d ON d.recording_id = r.id
            GROUP BY r.id
            ORDER BY r.recorded_at
            """
        ).fetchall()
    finally:
        connection.close()

    result = []
    project_root = database.parent.parent.parent
    for row in rows:
        item = dict(row)
        item["absolute_path"] = canonical_path(
            Path(str(row["file_path"])),
            recordings_root,
            project_root,
        )
        item["_timestamp"] = parse_timestamp(row["recorded_at"])
        result.append(item)
    return result


def nearest_row(
    path: Path,
    rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    candidate_time = timestamp_from_filename(path)
    if candidate_time is None or not rows:
        return None
    timed_rows = [row for row in rows if row["_timestamp"] is not None]
    if not timed_rows:
        return None
    match = min(
        timed_rows,
        key=lambda row: abs(
            (row["_timestamp"] - candidate_time).total_seconds()
        ),
    )
    return {
        "id": match["id"],
        "file_path": match["file_path"],
        "recorded_at": match["recorded_at"],
        "delta_seconds": round(
            abs((match["_timestamp"] - candidate_time).total_seconds()), 3
        ),
    }


def classify(
    path: Path,
    *,
    digest: str,
    referenced_checksums: dict[str, list[str]],
    orphan_checksums: dict[str, list[Path]],
    nearest: dict[str, Any] | None,
    recordings_root: Path,
) -> tuple[str, str, bool]:
    if path.stat().st_size == 0:
        return (
            "Ingestion failures",
            "Zero-byte WAV has no database row and contains no audio",
            True,
        )
    if digest in referenced_checksums:
        return (
            "Duplicate recordings",
            "SHA-256 matches a database-referenced WAV",
            True,
        )
    duplicates = orphan_checksums[digest]
    if len(duplicates) > 1:
        canonical = min(duplicates, key=lambda item: str(item))
        return (
            "Duplicate recordings",
            f"SHA-256 matches {len(duplicates) - 1} other orphan(s)",
            path != canonical,
        )

    relative = path.relative_to(recordings_root)
    if len(relative.parts) == 2:
        return (
            "Legacy recordings",
            "Pre-station directory layout: <date>/<file>",
            False,
        )

    file_time = timestamp_from_filename(path)
    if nearest and nearest["delta_seconds"] <= 2:
        return (
            "Missing DB rows",
            "Filename time is within 2 seconds of a different database row",
            False,
        )
    if file_time is not None:
        return (
            "Ingestion failures",
            "Valid current-layout recording has no database row",
            False,
        )
    return (
        "Unknown",
        "Filename and layout do not provide sufficient evidence",
        False,
    )


def build_inventory(
    database: Path,
    recordings_root: Path,
    *,
    settlement_seconds: int = 300,
) -> dict[str, Any]:
    database = database.resolve()
    recordings_root = recordings_root.resolve()
    # List files before reading rows. The recorder creates the WAV before it
    # commits its row, so this order prevents a live recording from appearing
    # as an orphan merely because it was captured between the two snapshots.
    wav_files = sorted(
        path.resolve()
        for path in recordings_root.rglob("*")
        if path.is_file() and path.suffix.lower() == ".wav"
    )
    rows = read_rows(database, recordings_root)
    referenced_paths = {row["absolute_path"] for row in rows}
    referenced_files = [
        path for path in wav_files if str(path) in referenced_paths
    ]
    unreferenced_files = [
        path for path in wav_files if str(path) not in referenced_paths
    ]
    settlement_cutoff = time.time() - settlement_seconds
    unsettled_files = [
        path
        for path in unreferenced_files
        if settlement_seconds > 0 and path.stat().st_mtime >= settlement_cutoff
    ]
    unsettled_paths = set(unsettled_files)
    orphan_files = [
        path for path in unreferenced_files if path not in unsettled_paths
    ]
    wav_paths = {str(path) for path in wav_files}

    referenced_checksums: dict[str, list[str]] = defaultdict(list)
    for path in referenced_files:
        referenced_checksums[checksum(path)].append(str(path))

    orphan_digests = {path: checksum(path) for path in orphan_files}
    orphan_checksums: dict[str, list[Path]] = defaultdict(list)
    for path, digest in orphan_digests.items():
        orphan_checksums[digest].append(path)

    orphans = []
    for path in orphan_files:
        stat = path.stat()
        creation_epoch = getattr(stat, "st_birthtime", stat.st_ctime)
        nearest = nearest_row(path, rows)
        category, evidence, safe = classify(
            path,
            digest=orphan_digests[path],
            referenced_checksums=referenced_checksums,
            orphan_checksums=orphan_checksums,
            nearest=nearest,
            recordings_root=recordings_root,
        )
        orphans.append(
            {
                "absolute_path": str(path),
                "size_bytes": stat.st_size,
                "creation_time": datetime.fromtimestamp(
                    creation_epoch, timezone.utc
                ).isoformat(),
                "creation_time_source": (
                    "birth_time"
                    if hasattr(stat, "st_birthtime")
                    else "ctime_metadata_change_time"
                ),
                "modification_time": datetime.fromtimestamp(
                    stat.st_mtime, timezone.utc
                ).isoformat(),
                "sha256": orphan_digests[path],
                "category": category,
                "classification_evidence": evidence,
                "safe_to_delete": safe,
                "nearest_database_row": nearest,
            }
        )

    categories = {
        name: {
            "count": sum(item["category"] == name for item in orphans),
            "size_bytes": sum(
                item["size_bytes"]
                for item in orphans
                if item["category"] == name
            ),
        }
        for name in CATEGORIES
    }
    safe = [item for item in orphans if item["safe_to_delete"]]
    unknown = [item for item in orphans if not item["safe_to_delete"]]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": str(database),
        "recordings_root": str(recordings_root),
        "summary": {
            "total_wav_files": len(wav_files),
            "referenced_wav_files": len(referenced_files),
            "orphaned_wav_files": len(orphan_files),
            "unsettled_wav_files": len(unsettled_files),
            "database_rows": len(rows),
            "database_rows_missing_files": sum(
                row["absolute_path"] not in wav_paths
                for row in rows
            ),
            "orphaned_size_bytes": sum(
                item["size_bytes"] for item in orphans
            ),
            "safe_to_delete_files": len(safe),
            "safe_to_delete_bytes": sum(
                item["size_bytes"] for item in safe
            ),
            "preserved_files": len(unknown),
            "preserved_bytes": sum(
                item["size_bytes"] for item in unknown
            ),
        },
        "categories": categories,
        "orphans": orphans,
        "unsettled_files": [str(path) for path in unsettled_files],
    }


def format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def print_inventory(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"Total WAV files: {summary['total_wav_files']}")
    print(f"Referenced WAV files: {summary['referenced_wav_files']}")
    print(f"Orphaned WAV files: {summary['orphaned_wav_files']}")
    print(f"Unsettled WAV files: {summary['unsettled_wav_files']}")
    print()
    print("Category | Count | Size")
    for name, values in report["categories"].items():
        print(f"{name} | {values['count']} | {format_bytes(values['size_bytes'])}")


def print_dry_run(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"Safe to delete: {summary['safe_to_delete_files']} files")
    print(
        "Space reclaimed: "
        f"{format_bytes(summary['safe_to_delete_bytes'])}"
    )
    print()
    print(f"Unknown files: {summary['preserved_files']}")
    print(
        "Space preserved: "
        f"{format_bytes(summary['preserved_bytes'])}"
    )
    print()
    print("Nothing was deleted.")


def parser() -> argparse.ArgumentParser:
    config = load_config()
    result = argparse.ArgumentParser(
        description="Reconcile WAV files with the Field Mouse database."
    )
    subparsers = result.add_subparsers(dest="command", required=True)
    for name in ("inventory", "dry-run-cleanup"):
        command = subparsers.add_parser(name)
        command.add_argument(
            "--database", type=Path, default=config.storage.database_path
        )
        command.add_argument(
            "--recordings-root",
            type=Path,
            default=config.storage.recordings_directory,
        )
        command.add_argument(
            "--output",
            type=Path,
            default=Path("audio-audit-report.json"),
        )
        command.add_argument(
            "--settlement-seconds",
            type=int,
            default=300,
            help="Exclude newer unreferenced WAVs that may still be recording.",
        )
    return result


def main(arguments: Iterable[str] | None = None) -> int:
    options = parser().parse_args(arguments)
    report = build_inventory(
        options.database,
        options.recordings_root,
        settlement_seconds=options.settlement_seconds,
    )
    options.output.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    if options.command == "inventory":
        print_inventory(report)
    else:
        print_dry_run(report)
    print(f"\nReport: {options.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
