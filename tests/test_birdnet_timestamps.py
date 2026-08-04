from __future__ import annotations

import sqlite3
from datetime import time, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from app.database.connection import initialize_database
from app.detectors.timestamps import parse_birdnet_timestamp


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (12, 12.0),
        (12.25, 12.25),
        ("12", 12.0),
        ("12.25", 12.25),
        ("00:12.25", 12.25),
        ("00:00:12.00", 12.0),
        ("01:02:03.50", 3723.5),
        (" 00:00:12.00 ", 12.0),
        (time(1, 2, 3, 500000), 3723.5),
        (timedelta(hours=1, minutes=2, seconds=3.5), 3723.5),
    ],
)
def test_parse_birdnet_timestamp_supported_formats(
    value: object,
    expected: float,
) -> None:
    assert parse_birdnet_timestamp(value) == pytest.approx(expected)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "not-a-time",
        "00:60:00",
        "00:00:60",
        "-1",
        "nan",
        "inf",
        True,
        None,
    ],
)
def test_parse_birdnet_timestamp_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ValueError, match="Invalid BirdNET timestamp"):
        parse_birdnet_timestamp(value)


def create_recording(
    database: Path,
    audio_path: Path,
    *,
    status: str,
) -> int:
    initialize_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO stations (id, name, timezone, created_at)
            VALUES ('station', 'Station', 'UTC', '2026-08-04T00:00:00Z')
            """
        )
        cursor = connection.execute(
            """
            INSERT INTO recordings (
                station_id, file_path, recorded_at, duration_seconds,
                sample_rate, channels, sample_format, file_size_bytes,
                processing_status, created_at
            )
            VALUES (?, ?, ?, 60, 48000, 1, 'S16_LE', 1, ?, ?)
            """,
            (
                "station",
                str(audio_path),
                "2026-08-04T00:00:00+00:00",
                status,
                "2026-08-04T00:00:00+00:00",
            ),
        )
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)


def formatted_prediction() -> dict[str, str]:
    return {
        "species_name": "Turdus migratorius_American Robin",
        "confidence": "0.91",
        "start_time": "00:00:12.00",
        "end_time": "00:00:15.50",
    }


def test_failed_recording_can_be_reprocessed_without_duplicates(
    tmp_path: Path,
) -> None:
    pytest.importorskip("birdnet")
    from app.detectors.process_recording import get_recording, save_detections

    database = tmp_path / "fieldmouse.db"
    recording_id = create_recording(
        database,
        tmp_path / "recording.wav",
        status="failed",
    )
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        recording = get_recording(connection, recording_id)
        assert recording["id"] == recording_id
        with patch(
            "app.detectors.process_recording.build_verification_manager",
            return_value=None,
        ):
            assert save_detections(
                connection,
                recording_id,
                [formatted_prediction()],
                0.25,
            ) == 1
            assert save_detections(
                connection,
                recording_id,
                [formatted_prediction()],
                0.25,
            ) == 1

        detection = connection.execute(
            "SELECT start_time, end_time FROM detections"
        ).fetchone()
        assert tuple(detection) == pytest.approx((12.0, 15.5))
        assert connection.execute(
            "SELECT COUNT(*) FROM detections"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT processing_status FROM recordings WHERE id = ?",
            (recording_id,),
        ).fetchone()[0] == "processed"
    finally:
        connection.close()


def test_worker_processes_formatted_timestamps_without_restart(
    tmp_path: Path,
) -> None:
    pytest.importorskip("birdnet")
    from app.services.detection_worker import process_next_recording

    database = tmp_path / "fieldmouse.db"
    audio_path = tmp_path / "recording.wav"
    audio_path.write_bytes(b"test")
    recording_id = create_recording(database, audio_path, status="pending")

    with (
        patch(
            "app.services.detection_worker.run_birdnet",
            return_value=[formatted_prediction()],
        ),
        patch(
            "app.detectors.process_recording.build_verification_manager",
            return_value=None,
        ),
    ):
        processed = process_next_recording(
            database_path=database,
            minimum_confidence=0.25,
            latitude=47.5,
            longitude=-122.6,
            occurrence_threshold=0.03,
        )

    assert processed is True
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT processing_status FROM recordings WHERE id = ?",
            (recording_id,),
        ).fetchone()[0] == "processed"
        assert connection.execute(
            "SELECT start_time, end_time FROM detections"
        ).fetchone() == pytest.approx((12.0, 15.5))


def test_parse_failure_rolls_back_partial_inserts_and_remains_recoverable(
    tmp_path: Path,
) -> None:
    pytest.importorskip("birdnet")
    from app.services.detection_worker import process_next_recording

    database = tmp_path / "fieldmouse.db"
    audio_path = tmp_path / "recording.wav"
    audio_path.write_bytes(b"test")
    recording_id = create_recording(database, audio_path, status="pending")
    malformed = {
        **formatted_prediction(),
        "species_name": "Corvus brachyrhynchos_American Crow",
        "start_time": "invalid",
    }

    with (
        patch(
            "app.services.detection_worker.run_birdnet",
            return_value=[formatted_prediction(), malformed],
        ),
        patch(
            "app.detectors.process_recording.build_verification_manager",
            return_value=None,
        ),
        pytest.raises(ValueError, match="Invalid BirdNET start_time"),
    ):
        process_next_recording(
            database_path=database,
            minimum_confidence=0.25,
            latitude=47.5,
            longitude=-122.6,
            occurrence_threshold=0.03,
        )

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM detections"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT processing_status FROM recordings WHERE id = ?",
            (recording_id,),
        ).fetchone()[0] == "failed"

    # The continuous worker selects pending recordings only. An administrator
    # retries a failed ID explicitly through process_recording.
    from app.detectors.process_recording import get_recording, save_detections

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        assert get_recording(connection, recording_id)["id"] == recording_id
        with patch(
            "app.detectors.process_recording.build_verification_manager",
            return_value=None,
        ):
            save_detections(
                connection,
                recording_id,
                [formatted_prediction()],
                0.25,
            )
        assert connection.execute(
            "SELECT processing_status FROM recordings WHERE id = ?",
            (recording_id,),
        ).fetchone()[0] == "processed"
        assert connection.execute(
            "SELECT COUNT(*) FROM detections"
        ).fetchone()[0] == 1
    finally:
        connection.close()
