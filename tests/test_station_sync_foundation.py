from __future__ import annotations

import hashlib
import shutil
import sqlite3
import subprocess
import uuid
from pathlib import Path

import pytest

from app.audio import recorder
from app.config import ConfigurationError, FieldMouseConfig, load_config
from app.database.connection import (
    DatabaseError,
    connect_database,
    insert_recording,
    upsert_station,
)
from app.migrations import MIGRATIONS_DIRECTORY, migrate


NOW = "2026-10-15T12:00:00+00:00"
STATION_UUID = "95ad5867-2f5b-4b98-8ab6-b45686238b85"


def write_config(path: Path, tmp_path: Path, station_uuid: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    uuid_line = "" if station_uuid is None else f'uuid = "{station_uuid}"\n'
    path.write_text(
        "[station]\n"
        'id = "station-sync-test"\n'
        f"{uuid_line}"
        'name = "Sync Test"\n'
        'timezone = "UTC"\n'
        "[storage]\n"
        f'database_path = "{(tmp_path / "fieldmouse.db").as_posix()}"\n'
        f'recordings_directory = "{(tmp_path / "recordings").as_posix()}"\n',
        encoding="utf-8",
    )


def config_for(
    tmp_path: Path,
    station_uuid: str | None = STATION_UUID,
) -> FieldMouseConfig:
    config_path = tmp_path / "station.toml"
    write_config(config_path, tmp_path, station_uuid)
    return load_config(config_path, {})


def open_database(
    tmp_path: Path,
    station_uuid: str = STATION_UUID,
) -> tuple[sqlite3.Connection, Path]:
    database = tmp_path / "fieldmouse.db"
    migrate(database, tmp_path / "backups")
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        """
        INSERT INTO stations (id, name, timezone, created_at, station_uuid)
        VALUES ('station-sync-test', 'Sync Test', 'UTC', ?, ?)
        """,
        (NOW, station_uuid),
    )
    connection.commit()
    return connection, database


def insert_sync_recording(
    connection: sqlite3.Connection,
    tmp_path: Path,
    *,
    filename: str = "recording.wav",
    content: bytes = b"RIFF" + b"audio" * 100,
) -> int:
    audio = tmp_path / filename
    audio.write_bytes(content)
    return insert_recording(
        connection,
        station_id="station-sync-test",
        file_path=audio,
        recorded_at=NOW,
        duration_seconds=60,
        sample_rate=48000,
        channels=1,
        sample_format="S16_LE",
        file_size_bytes=audio.stat().st_size,
        content_sha256=hashlib.sha256(content).hexdigest(),
        station_uuid=STATION_UUID,
    )


def test_valid_station_uuid_is_canonical_and_stable_across_reload(
    tmp_path: Path,
) -> None:
    upper = STATION_UUID.upper()
    config_path = tmp_path / "station.toml"
    write_config(config_path, tmp_path, upper)

    first = load_config(config_path, {})
    second = load_config(config_path, {})

    assert first.station.uuid == STATION_UUID
    assert second.station.uuid == STATION_UUID


def test_absent_station_uuid_keeps_non_sync_configuration_compatible(
    tmp_path: Path,
) -> None:
    config = config_for(tmp_path, None)
    assert config.station.uuid == ""


@pytest.mark.parametrize("value", ["not-a-uuid", "00000000-0000-0000-0000-000000000000"])
def test_invalid_station_uuid_is_rejected(tmp_path: Path, value: str) -> None:
    config_path = tmp_path / "station.toml"
    write_config(config_path, tmp_path, value)
    with pytest.raises(ConfigurationError, match="station UUID"):
        load_config(config_path, {})


def test_station_uuid_is_not_erased_or_replaced(tmp_path: Path) -> None:
    config = config_for(tmp_path)
    migrate(config.storage.database_path, tmp_path / "backups")
    with connect_database(config.storage.database_path) as connection:
        upsert_station(connection, config)
        connection.commit()
        absent = config_for(tmp_path / "absent", None)
        upsert_station(connection, absent)
        connection.commit()
        stored = connection.execute(
            "SELECT station_uuid FROM stations WHERE id = ?", (config.station.id,)
        ).fetchone()[0]
        assert stored == STATION_UUID
        with pytest.raises(sqlite3.IntegrityError, match="station UUID is immutable"):
            connection.execute(
                "UPDATE stations SET station_uuid = ? WHERE id = ?",
                (str(uuid.uuid4()), config.station.id),
            )


def test_recording_identity_is_unique_immutable_and_persistent(tmp_path: Path) -> None:
    connection, database = open_database(tmp_path)
    first = insert_sync_recording(connection, tmp_path, filename="one.wav")
    second = insert_sync_recording(connection, tmp_path, filename="two.wav")
    connection.commit()
    identities = [
        row[0]
        for row in connection.execute("SELECT recording_identity FROM recordings ORDER BY id")
    ]
    assert first != second
    assert len(set(identities)) == 2
    assert all(uuid.UUID(identity) for identity in identities)
    with pytest.raises(sqlite3.IntegrityError, match="identity is immutable"):
        connection.execute(
            "UPDATE recordings SET recording_identity = ? WHERE id = ?",
            (str(uuid.uuid4()), first),
        )
    connection.close()
    with sqlite3.connect(database) as reopened:
        assert (
            reopened.execute(
                "SELECT recording_identity FROM recordings WHERE id = ?", (first,)
            ).fetchone()[0]
            == identities[0]
        )


def test_identical_bytes_keep_distinct_recording_identities(tmp_path: Path) -> None:
    connection, _ = open_database(tmp_path)
    insert_sync_recording(connection, tmp_path, filename="one.wav")
    insert_sync_recording(connection, tmp_path, filename="two.wav")
    rows = connection.execute(
        "SELECT recording_identity, content_sha256 FROM recordings ORDER BY id"
    ).fetchall()
    assert rows[0][0] != rows[1][0]
    assert rows[0][1] == rows[1][1]


def test_content_sha256_hashes_exact_wav_bytes_and_is_immutable(tmp_path: Path) -> None:
    content = b"RIFF" + bytes(range(256)) * 4
    audio = tmp_path / "exact.wav"
    audio.write_bytes(content)
    assert recorder.calculate_content_sha256(audio) == hashlib.sha256(content).hexdigest()
    connection, _ = open_database(tmp_path / "database")
    recording_id = insert_sync_recording(
        connection,
        tmp_path / "database",
        content=content,
    )
    with pytest.raises(sqlite3.IntegrityError, match="SHA-256 is immutable"):
        connection.execute(
            "UPDATE recordings SET content_sha256 = ? WHERE id = ?",
            ("0" * 64, recording_id),
        )


def _successful_arecord(command: list[str], *, check: bool) -> subprocess.CompletedProcess:
    assert check is True
    Path(command[-1]).write_bytes(b"RIFF" + b"captured-audio" * 100)
    return subprocess.CompletedProcess(command, 0)


def test_successful_capture_atomically_creates_one_pending_intent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = config_for(tmp_path)
    monkeypatch.setattr(recorder.subprocess, "run", _successful_arecord)

    output = recorder.record_audio(config, duration_override=1)

    with sqlite3.connect(config.storage.database_path) as connection:
        row = connection.execute(
            """
            SELECT recording.recording_identity, recording.content_sha256,
                   outbox.recording_identity, outbox.station_uuid, outbox.state,
                   outbox.attempt_count
            FROM recordings AS recording
            JOIN station_sync_outbox AS outbox
              ON outbox.recording_id = recording.id
            """
        ).fetchone()
        assert row == (
            row[0],
            hashlib.sha256(output.read_bytes()).hexdigest(),
            row[0],
            STATION_UUID,
            "PENDING",
            0,
        )
        assert connection.execute("SELECT COUNT(*) FROM station_sync_outbox").fetchone()[0] == 1


def test_absent_uuid_capture_persists_checksum_without_outbox(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = config_for(tmp_path, None)
    monkeypatch.setattr(recorder.subprocess, "run", _successful_arecord)
    output = recorder.record_audio(config, duration_override=1)
    with sqlite3.connect(config.storage.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM recordings").fetchone()[0] == 1
        assert (
            connection.execute("SELECT content_sha256 FROM recordings").fetchone()[0]
            == hashlib.sha256(output.read_bytes()).hexdigest()
        )
        assert connection.execute("SELECT COUNT(*) FROM station_sync_outbox").fetchone()[0] == 0


def test_failed_capture_removes_partial_file_and_creates_no_database_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = config_for(tmp_path)
    output = tmp_path / "failed.wav"
    monkeypatch.setattr(recorder, "create_recording_path", lambda *args, **kwargs: output)

    def fail(command: list[str], *, check: bool) -> None:
        output.write_bytes(b"partial")
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(recorder.subprocess, "run", fail)
    with pytest.raises(RuntimeError, match="Recording failed"):
        recorder.record_audio(config, duration_override=1)
    assert not output.exists()
    assert not config.storage.database_path.exists()


def test_failed_validation_creates_no_outbox_and_removes_wav(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = config_for(tmp_path)
    output = tmp_path / "invalid.wav"
    monkeypatch.setattr(recorder, "create_recording_path", lambda *args, **kwargs: output)

    def invalid(command: list[str], *, check: bool) -> None:
        output.write_bytes(b"RIFF")

    monkeypatch.setattr(recorder.subprocess, "run", invalid)
    with pytest.raises(RuntimeError, match="no usable audio"):
        recorder.record_audio(config, duration_override=1)
    assert not output.exists()
    assert not config.storage.database_path.exists()


def test_checksum_failure_creates_no_outbox_and_removes_wav(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = config_for(tmp_path)
    monkeypatch.setattr(recorder.subprocess, "run", _successful_arecord)
    monkeypatch.setattr(
        recorder,
        "calculate_content_sha256",
        lambda path: (_ for _ in ()).throw(RuntimeError("hash failed")),
    )
    with pytest.raises(RuntimeError, match="hash failed"):
        recorder.record_audio(config, duration_override=1)
    assert not config.storage.database_path.exists()
    assert list(config.storage.recordings_directory.rglob("*.wav")) == []


def test_failed_outbox_insert_rolls_back_recording_and_source_event(
    tmp_path: Path,
) -> None:
    connection, _ = open_database(tmp_path)
    audio = tmp_path / "mismatch.wav"
    content = b"RIFF" + b"audio" * 100
    audio.write_bytes(content)
    with pytest.raises(DatabaseError, match="outbox identity"):
        insert_recording(
            connection,
            station_id="station-sync-test",
            file_path=audio,
            recorded_at=NOW,
            duration_seconds=60,
            sample_rate=48000,
            channels=1,
            sample_format="S16_LE",
            file_size_bytes=len(content),
            content_sha256=hashlib.sha256(content).hexdigest(),
            station_uuid=str(uuid.uuid4()),
        )
    assert connection.execute("SELECT COUNT(*) FROM recordings").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM recording_source_events").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM station_sync_outbox").fetchone()[0] == 0


def test_pending_intent_survives_restart_and_fk_is_restricted(tmp_path: Path) -> None:
    connection, database = open_database(tmp_path)
    recording_id = insert_sync_recording(connection, tmp_path)
    connection.commit()
    connection.close()
    with sqlite3.connect(database) as reopened:
        reopened.execute("PRAGMA foreign_keys = ON")
        assert (
            reopened.execute(
                "SELECT state FROM station_sync_outbox WHERE recording_id = ?",
                (recording_id,),
            ).fetchone()[0]
            == "PENDING"
        )
        with pytest.raises(sqlite3.IntegrityError):
            reopened.execute("DELETE FROM recordings WHERE id = ?", (recording_id,))


def test_outbox_rejects_duplicate_or_inconsistent_identity(tmp_path: Path) -> None:
    connection, _ = open_database(tmp_path)
    recording_id = insert_sync_recording(connection, tmp_path)
    row = connection.execute(
        "SELECT recording_identity FROM recordings WHERE id = ?", (recording_id,)
    ).fetchone()
    now = NOW
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO station_sync_outbox (
                recording_id, recording_identity, station_uuid, state,
                attempt_count, created_at, updated_at
            ) VALUES (?, ?, ?, 'PENDING', 0, ?, ?)
            """,
            (recording_id, row[0], STATION_UUID, now, now),
        )
    with pytest.raises(sqlite3.IntegrityError, match="outbox identity"):
        connection.execute(
            """
            INSERT INTO station_sync_outbox (
                recording_id, recording_identity, station_uuid, state,
                attempt_count, created_at, updated_at
            ) VALUES (999, ?, ?, 'PENDING', 0, ?, ?)
            """,
            (str(uuid.uuid4()), STATION_UUID, now, now),
        )


def test_outbox_identity_is_immutable_and_ack_requires_durable_timestamp(
    tmp_path: Path,
) -> None:
    connection, _ = open_database(tmp_path)
    recording_id = insert_sync_recording(connection, tmp_path)
    with pytest.raises(sqlite3.IntegrityError, match="identity fields are immutable"):
        connection.execute(
            "UPDATE station_sync_outbox SET station_uuid = ? WHERE recording_id = ?",
            (str(uuid.uuid4()), recording_id),
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE station_sync_outbox SET state = 'ACKNOWLEDGED' WHERE recording_id = ?",
            (recording_id,),
        )
    acknowledged_at = "2026-10-15T13:00:00+00:00"
    connection.execute(
        """
        UPDATE station_sync_outbox
        SET state = 'ACKNOWLEDGED', server_acknowledged_at = ?, updated_at = ?
        WHERE recording_id = ?
        """,
        (acknowledged_at, acknowledged_at, recording_id),
    )
    assert tuple(
        connection.execute(
            "SELECT state, server_acknowledged_at FROM station_sync_outbox"
        ).fetchone()
    ) == ("ACKNOWLEDGED", acknowledged_at)
    with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
        connection.execute(
            "DELETE FROM station_sync_outbox WHERE recording_id = ?", (recording_id,)
        )


def test_historical_migration_is_stable_and_scientifically_non_destructive(
    tmp_path: Path,
) -> None:
    old_migrations = tmp_path / "old-migrations"
    old_migrations.mkdir()
    for source in sorted(MIGRATIONS_DIRECTORY.glob("*.sql")):
        if source.name.startswith("0011_"):
            continue
        shutil.copy2(source, old_migrations / source.name)
    database = tmp_path / "legacy.db"
    migrate(database, tmp_path / "backups", old_migrations)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            INSERT INTO stations (id, name, timezone, created_at)
            VALUES ('legacy', 'Legacy', 'UTC', ?)
            """,
            (NOW,),
        )
        connection.execute(
            """
            INSERT INTO recordings (
                id, station_id, file_path, recorded_at, duration_seconds,
                sample_rate, channels, sample_format, file_size_bytes,
                processing_status, created_at
            ) VALUES (41, 'legacy', 'missing.wav', ?, 60, 48000, 1,
                      'S16_LE', 500, 'processed', ?)
            """,
            (NOW, NOW),
        )
        connection.execute(
            """
            INSERT INTO detections (
                id, recording_id, detector, common_name, scientific_name,
                confidence, start_time, end_time, created_at
            ) VALUES (51, 41, 'birdnet', 'Robin', 'Turdus migratorius',
                      0.9, 1, 4, ?)
            """,
            (NOW,),
        )
        connection.execute(
            """
            INSERT INTO recording_protections (
                recording_id, protection_type, origin_type, origin_reference,
                origin_evidence_id, reason_code, reason, created_by, created_at
            ) VALUES (41, 'MANUALLY_PINNED', 'MANUAL', 'legacy-test', NULL,
                      'TEST', 'Preserve source', 'TEST', ?)
            """,
            (NOW,),
        )
        before_availability = connection.execute(
            "SELECT source_availability FROM recordings WHERE id = 41"
        ).fetchone()[0]
        before_protection = connection.execute("SELECT * FROM recording_protections").fetchone()
        connection.commit()

    applied = migrate(database, tmp_path / "backups")
    assert [item.version for item in applied] == [11]
    with sqlite3.connect(database) as connection:
        identity, checksum, availability = connection.execute(
            """
            SELECT recording_identity, content_sha256, source_availability
            FROM recordings WHERE id = 41
            """
        ).fetchone()
        first_identity = identity
        assert uuid.UUID(identity)
        assert checksum is None
        assert availability == before_availability
        assert (
            connection.execute("SELECT * FROM recording_protections").fetchone()
            == before_protection
        )
        assert (
            connection.execute("SELECT recording_id FROM detections WHERE id = 51").fetchone()[0]
            == 41
        )
        assert connection.execute("SELECT COUNT(*) FROM station_sync_outbox").fetchone()[0] == 0
        assert (
            connection.execute("SELECT station_uuid FROM stations WHERE id = 'legacy'").fetchone()[
                0
            ]
            is None
        )
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    assert migrate(database, tmp_path / "backups") == []
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute(
                "SELECT recording_identity FROM recordings WHERE id = 41"
            ).fetchone()[0]
            == first_identity
        )
