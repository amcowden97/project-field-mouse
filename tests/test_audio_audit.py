from __future__ import annotations

import sqlite3
import wave
from pathlib import Path

from app.audio_audit import build_inventory, main


def create_wav(path: Path, content: bytes = b"\0\0" * 10) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8_000)
        stream.writeframes(content)


def create_database(path: Path, referenced: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE recordings (
            id INTEGER PRIMARY KEY,
            file_path TEXT,
            recorded_at TEXT,
            created_at TEXT,
            processing_status TEXT,
            file_size_bytes INTEGER
        );
        CREATE TABLE detections (
            id INTEGER PRIMARY KEY,
            recording_id INTEGER
        );
        """
    )
    connection.execute(
        """
        INSERT INTO recordings VALUES
        (1, ?, '2026-07-30T12:00:00+00:00',
         '2026-07-30T12:01:00+00:00', 'processed', ?)
        """,
        (
            str(referenced),
            referenced.stat().st_size if referenced.exists() else 0,
        ),
    )
    connection.commit()
    connection.close()


def test_inventory_classifies_duplicate_and_ingestion_failure(
    tmp_path: Path,
) -> None:
    root = tmp_path / "recordings"
    referenced = (
        root / "station" / "2026-07-30" / "2026-07-30T12-00-00+0000.wav"
    )
    duplicate = (
        root / "station" / "2026-07-30" / "2026-07-30T12-01-00+0000.wav"
    )
    failure = (
        root / "station" / "2026-07-30" / "2026-07-30T12-02-00+0000.wav"
    )
    create_wav(referenced)
    create_wav(duplicate)
    create_wav(failure, b"\1\0" * 10)
    database = tmp_path / "fieldmouse.db"
    create_database(database, referenced)

    report = build_inventory(database, root, settlement_seconds=0)

    assert report["summary"]["total_wav_files"] == 3
    assert report["summary"]["referenced_wav_files"] == 1
    assert report["summary"]["orphaned_wav_files"] == 2
    assert report["categories"]["Duplicate recordings"]["count"] == 1
    assert report["categories"]["Ingestion failures"]["count"] == 1
    assert report["summary"]["safe_to_delete_files"] == 1


def test_dry_run_writes_report_without_deleting(
    tmp_path: Path,
) -> None:
    root = tmp_path / "recordings"
    referenced = root / "station" / "2026-07-30" / "known.wav"
    orphan = root / "2026-07-20" / "legacy.wav"
    create_wav(referenced)
    create_wav(orphan, b"\2\0" * 10)
    database = tmp_path / "fieldmouse.db"
    create_database(database, referenced)
    output = tmp_path / "report.json"

    assert main(
        [
            "dry-run-cleanup",
            "--database",
            str(database),
            "--recordings-root",
            str(root),
            "--output",
            str(output),
        ]
    ) == 0

    assert orphan.exists()
    assert referenced.exists()
    assert output.exists()


def test_project_relative_database_path_is_referenced(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data" / "recordings"
    referenced = root / "station" / "known.wav"
    create_wav(referenced)
    database = tmp_path / "data" / "database" / "fieldmouse.db"
    database.parent.mkdir(parents=True)
    create_database(database, Path("data/recordings/station/known.wav"))

    report = build_inventory(database, root, settlement_seconds=0)

    assert report["summary"]["referenced_wav_files"] == 1
    assert report["summary"]["orphaned_wav_files"] == 0


def test_zero_byte_orphan_is_safe_and_recent_file_is_unsettled(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data" / "recordings"
    referenced = root / "station" / "known.wav"
    zero = root / "station" / "2026-01-01T00-00-00+0000.wav"
    create_wav(referenced)
    zero.parent.mkdir(parents=True, exist_ok=True)
    zero.touch()
    database = tmp_path / "data" / "database" / "fieldmouse.db"
    database.parent.mkdir(parents=True)
    create_database(database, referenced)

    unsettled = build_inventory(database, root, settlement_seconds=300)
    classified = build_inventory(database, root, settlement_seconds=0)

    assert unsettled["summary"]["unsettled_wav_files"] == 1
    assert classified["summary"]["safe_to_delete_files"] == 1
