from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from app.services.storage_cleanup import expire_recording_audio, get_candidates


def test_rare_species_are_never_cleanup_candidates() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE recordings (
            id INTEGER PRIMARY KEY,
            file_path TEXT,
            recorded_at TEXT,
            processing_status TEXT
        );
        CREATE TABLE detections (
            id INTEGER PRIMARY KEY,
            recording_id INTEGER,
            common_name TEXT
        );
        """
    )
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    connection.execute(
        "INSERT INTO recordings VALUES (1, 'rare.wav', ?, 'processed')",
        (old,),
    )
    connection.execute(
        "INSERT INTO recordings VALUES (2, 'common.wav', ?, 'processed')",
        (old,),
    )
    connection.execute(
        "INSERT INTO detections VALUES (1, 1, 'Special Bird')"
    )
    connection.execute(
        "INSERT INTO detections VALUES (2, 2, 'Common Bird')"
    )

    candidates = get_candidates(
        connection,
        empty_cutoff=datetime.now(timezone.utc) - timedelta(days=1),
        detection_cutoff=datetime.now(timezone.utc) - timedelta(days=3),
        rare_species=frozenset({"special bird"}),
    )

    assert [row["id"] for row in candidates] == [2]


def test_empty_rare_list_preserves_all_detected_recordings() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE recordings (
            id INTEGER PRIMARY KEY,
            file_path TEXT,
            recorded_at TEXT,
            processing_status TEXT
        );
        CREATE TABLE detections (
            id INTEGER PRIMARY KEY,
            recording_id INTEGER,
            common_name TEXT
        );
        INSERT INTO recordings VALUES
            (1, 'detected.wav', '2026-01-01T00:00:00+00:00', 'processed');
        INSERT INTO detections VALUES (1, 1, 'Unclassified Bird');
        """
    )

    candidates = get_candidates(
        connection,
        empty_cutoff=datetime.now(timezone.utc),
        detection_cutoff=datetime.now(timezone.utc),
    )

    assert candidates == []


def test_expiration_preserves_database_history(tmp_path) -> None:
    audio_path = tmp_path / "recording.wav"
    audio_path.write_bytes(b"audio")
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE recordings (
            id INTEGER PRIMARY KEY,
            processing_status TEXT
        );
        CREATE TABLE detections (
            id INTEGER PRIMARY KEY,
            recording_id INTEGER REFERENCES recordings(id)
        );
        INSERT INTO recordings VALUES (1, 'processed');
        INSERT INTO detections VALUES (1, 1);
        """
    )

    deleted, freed = expire_recording_audio(
        connection,
        recording_id=1,
        audio_path=audio_path,
    )

    assert deleted is True
    assert freed == 5
    assert not audio_path.exists()
    assert connection.execute(
        "SELECT processing_status FROM recordings WHERE id = 1"
    ).fetchone()[0] == "audio_expired"
    assert connection.execute(
        "SELECT COUNT(*) FROM detections WHERE recording_id = 1"
    ).fetchone()[0] == 1

    deleted_again, freed_again = expire_recording_audio(
        connection,
        recording_id=1,
        audio_path=audio_path,
    )
    assert deleted_again is False
    assert freed_again == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM recordings WHERE id = 1"
    ).fetchone()[0] == 1
