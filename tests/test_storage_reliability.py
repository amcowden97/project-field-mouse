from __future__ import annotations

import json
import subprocess
import sqlite3
from datetime import datetime, timezone

from app.system.notifications import notify_state_change
from app.system.release_retention import prune_inactive_releases
from app.system.storage_health import storage_forecast, storage_state
from app.system.storage_recovery import recover_storage
from app.services.storage_cleanup import expire_recording_audio, get_candidates
from app.system.health_check import _database


def completed(arguments: list[str], returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(arguments, returncode, "", "")


def test_storage_watermarks_are_graduated() -> None:
    assert storage_state(79.9) == "normal"
    assert storage_state(80) == "advisory"
    assert storage_state(90) == "warning"
    assert storage_state(95) == "critical"
    assert storage_state(98) == "emergency"


def test_forecast_reports_time_and_date() -> None:
    now = datetime(2026, 8, 18, tzinfo=timezone.utc)
    result = storage_forecast(86400, 1.0, now=now)
    assert result["bytes_per_day"] == 86400
    assert result["seconds_remaining"] == 86400
    assert result["estimated_full_at"] == "2026-08-19T00:00:00+00:00"


def test_emergency_recovery_suspends_backup_cleans_and_starts_recorder() -> None:
    calls: list[list[str]] = []

    def run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        if arguments[1:3] == ["is-active", "fieldmouse-recorder.service"]:
            return completed(arguments, 3)
        return completed(arguments)

    result = recover_storage("emergency", run)

    assert result["cleanup_succeeded"] is True
    assert result["actions"] == [
        "backup_timer_suspended",
        "cleanup_attempted",
        "recorder_started",
    ]
    assert ["systemctl", "start", "fieldmouse-cleanup.service"] in calls


def test_notification_is_sent_only_when_conditions_change(tmp_path, monkeypatch) -> None:
    delivered = []
    monkeypatch.setattr(
        "app.system.notifications.send_webhook",
        lambda url, event, timeout: delivered.append(event) or True,
    )
    state = tmp_path / "notification.json"
    arguments = {
        "url": "https://alerts.invalid/hook",
        "state_path": state,
        "station_id": "station-a",
        "conditions": ["recording_stalled"],
        "detail": {"age": 100},
    }
    assert notify_state_change(**arguments) is True
    assert notify_state_change(**arguments) is False
    assert len(delivered) == 1
    assert json.loads(state.read_text())["conditions"] == ["recording_stalled"]


def test_release_retention_protects_current_previous_and_one_inactive(tmp_path) -> None:
    releases = tmp_path / "releases"
    releases.mkdir()
    paths = [releases / name for name in ("current", "previous", "newer", "old")]
    for modified, path in zip((4, 3, 2, 1), paths):
        path.mkdir()
        (path / "marker").write_text(path.name)
        path.touch()
        import os
        os.utime(path, (modified, modified))

    removed = prune_inactive_releases(
        releases,
        {paths[0], paths[1]},
        keep_inactive=1,
        apply=True,
    )

    assert removed == [paths[3]]
    assert all(path.exists() for path in paths[:3])
    assert not paths[3].exists()


def test_simulated_low_storage_cleanup_and_pipeline_recovery(tmp_path) -> None:
    database = tmp_path / "fieldmouse.db"
    audio = tmp_path / "old.wav"
    audio.write_bytes(b"old audio")
    now = datetime.now(timezone.utc)
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        connection.executescript(
            """
            CREATE TABLE recordings (
                id INTEGER PRIMARY KEY, file_path TEXT, recorded_at TEXT,
                processing_status TEXT, file_size_bytes INTEGER
            );
            CREATE TABLE detections (
                id INTEGER PRIMARY KEY, recording_id INTEGER, common_name TEXT,
                created_at TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO recordings VALUES (1, ?, ?, 'processed', 9)",
            (str(audio), "2026-01-01T00:00:00+00:00"),
        )
        candidates = get_candidates(
            connection,
            empty_cutoff=now,
            detection_cutoff=now,
            limit=100,
        )
        assert [row["id"] for row in candidates] == [1]
        expire_recording_audio(connection, recording_id=1, audio_path=audio)
        connection.execute(
            "INSERT INTO recordings VALUES (2, ?, ?, 'processed', 5760044)",
            (str(tmp_path / "new.wav"), now.isoformat()),
        )
        connection.commit()
    calls = []
    result = recover_storage(
        "critical",
        lambda arguments: calls.append(arguments) or completed(arguments),
    )
    health = _database(database)
    assert result["cleanup_succeeded"] is True
    assert not audio.exists()
    assert health["latest_recording_age_seconds"] < 5
    assert health["latest_processed_age_seconds"] < 5
    assert health["queue_depth"] == 0
