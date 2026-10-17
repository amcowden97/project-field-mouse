from __future__ import annotations

import hashlib
import shutil
import sqlite3
import threading
import uuid
from dataclasses import replace
from pathlib import Path

import pytest

from app.database.connection import connect_database, insert_recording
from app.migrations import MIGRATIONS_DIRECTORY, migrate
from app.science.recordings import SourceAvailability, set_source_availability
from app.server_ingestion import (
    ConflictReason,
    IngestionDomainError,
    IngestionOutcome,
    IngestionPersistenceError,
    IngestionState,
    RecordingDeclaration,
    ValidationErrorCode,
    declare_recording,
    ingestion_summary,
    last_declarations_by_station,
)


NOW = "2026-10-15T19:00:00+00:00"
SECOND = "2026-10-15T19:01:00+00:00"
STATION_UUID = "95ad5867-2f5b-4b98-8ab6-b45686238b85"
OTHER_STATION_UUID = "bdcd8019-23b5-4aad-aefe-ef9ff81529ea"
RECORDING_IDENTITY = "d53cbca1-1f2c-467e-918f-3089b1cccead"
CONTENT = b"RIFF" + b"server-ingestion" * 100
CHECKSUM = hashlib.sha256(CONTENT).hexdigest()

SCIENTIFIC_TABLES = (
    "recordings",
    "recording_source_events",
    "detections",
    "evidence",
    "reviews",
    "assessments",
    "ground_truth_datasets",
    "ground_truth_members",
    "ground_truth_adjudications",
    "recording_protections",
)


def open_database(tmp_path: Path) -> tuple[sqlite3.Connection, Path]:
    database = tmp_path / "fieldmouse.db"
    migrate(database, tmp_path / "backups")
    connection = connect_database(database)
    connection.execute(
        """
        INSERT INTO stations (id, name, timezone, created_at, station_uuid)
        VALUES ('station-one', 'Station One', 'UTC', ?, ?)
        """,
        (NOW, STATION_UUID),
    )
    connection.commit()
    return connection, database


def declaration(**overrides: object) -> RecordingDeclaration:
    values: dict[str, object] = {
        "station_uuid": STATION_UUID,
        "recording_identity": RECORDING_IDENTITY,
        "recorded_at": NOW,
        "content_sha256": CHECKSUM,
        "file_size_bytes": len(CONTENT),
        "duration_seconds": 60.0,
        "sample_rate": 48_000,
        "channels": 1,
        "sample_format": "S16_LE",
        "media_type": "audio/wav",
    }
    values.update(overrides)
    return RecordingDeclaration(**values)  # type: ignore[arg-type]


def scientific_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in SCIENTIFIC_TABLES
    }


def add_existing_recording(
    connection: sqlite3.Connection,
    tmp_path: Path,
    *,
    identity: str = RECORDING_IDENTITY,
    checksum: str | None = CHECKSUM,
    availability: SourceAvailability = SourceAvailability.AVAILABLE,
    **overrides: object,
) -> int:
    audio = tmp_path / f"{identity}.wav"
    audio.write_bytes(CONTENT)
    values = {
        "recorded_at": NOW,
        "duration_seconds": 60,
        "sample_rate": 48_000,
        "channels": 1,
        "sample_format": "S16_LE",
        "file_size_bytes": len(CONTENT),
    }
    values.update(overrides)
    recording_id = insert_recording(
        connection,
        station_id="station-one",
        file_path=audio,
        recorded_at=str(values["recorded_at"]),
        duration_seconds=int(values["duration_seconds"]),
        sample_rate=int(values["sample_rate"]),
        channels=int(values["channels"]),
        sample_format=str(values["sample_format"]),
        file_size_bytes=int(values["file_size_bytes"]),
        recording_identity=identity,
        content_sha256=checksum,
    )
    if availability is not SourceAvailability.AVAILABLE:
        set_source_availability(
            connection,
            recording_id=recording_id,
            availability=availability,
            reason_code=f"TEST_{availability.value}",
            authorized_by="TEST",
            authorization_reference="server-ingestion-test",
            operation_id=f"server-ingestion-{recording_id}-{availability.value}",
            occurred_at=SECOND,
        )
    return recording_id


def test_fresh_database_has_migration_0012_and_required_constraints(tmp_path: Path) -> None:
    connection, _ = open_database(tmp_path)
    assert (
        connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        ).fetchone()[0]
        == 12
    )
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(server_recording_ingestions)")
    }
    assert {
        "ingestion_id",
        "station_id",
        "station_uuid",
        "recording_identity",
        "content_sha256",
        "state",
        "recording_id",
        "declaration_count",
        "completed_at",
    } <= columns


def test_migration_0011_to_0012_is_schema_only_and_idempotent(tmp_path: Path) -> None:
    old_migrations = tmp_path / "through-0011"
    old_migrations.mkdir()
    for source in sorted(MIGRATIONS_DIRECTORY.glob("*.sql")):
        if int(source.name[:4]) <= 11:
            shutil.copy2(source, old_migrations / source.name)
    database = tmp_path / "legacy.db"
    migrate(database, tmp_path / "backups", old_migrations)
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        """
        INSERT INTO stations (id, name, timezone, created_at, station_uuid)
        VALUES ('station-one', 'Station One', 'UTC', ?, ?)
        """,
        (NOW, STATION_UUID),
    )
    add_existing_recording(connection, tmp_path, checksum=None)
    before_recording = tuple(connection.execute("SELECT * FROM recordings").fetchone())
    before_counts = scientific_counts(connection)
    before_availability = dict(
        connection.execute(
            "SELECT source_availability, COUNT(*) FROM recordings GROUP BY source_availability"
        )
    )
    connection.commit()
    connection.close()

    applied = migrate(database, tmp_path / "backups")
    assert [(item.version, item.name) for item in applied] == [
        (12, "server_ingestion_metadata_foundation")
    ]
    assert migrate(database, tmp_path / "backups") == []
    with sqlite3.connect(database) as migrated:
        assert tuple(migrated.execute("SELECT * FROM recordings").fetchone()) == before_recording
        assert scientific_counts(migrated) == before_counts
        assert (
            dict(
                migrated.execute(
                    "SELECT source_availability, COUNT(*) FROM recordings GROUP BY source_availability"
                )
            )
            == before_availability
        )
        assert migrated.execute("SELECT content_sha256 FROM recordings").fetchone()[0] is None
        assert (
            migrated.execute("SELECT COUNT(*) FROM server_recording_ingestions").fetchone()[0] == 0
        )
        assert migrated.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert migrated.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize(
    ("station_uuid", "code"),
    [
        (str(uuid.uuid4()), ValidationErrorCode.UNKNOWN_STATION_UUID),
        ("not-a-uuid", ValidationErrorCode.INVALID_STATION_UUID),
        ("00000000-0000-0000-0000-000000000000", ValidationErrorCode.INVALID_STATION_UUID),
        ("station-one", ValidationErrorCode.INVALID_STATION_UUID),
    ],
)
def test_unknown_malformed_nil_and_human_station_ids_fail_without_persistence(
    tmp_path: Path,
    station_uuid: str,
    code: ValidationErrorCode,
) -> None:
    connection, _ = open_database(tmp_path)
    with pytest.raises(IngestionDomainError) as raised:
        declare_recording(connection, declaration(station_uuid=station_uuid))
    assert raised.value.code is code
    assert connection.execute("SELECT COUNT(*) FROM server_recording_ingestions").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"recording_identity": "bad"}, ValidationErrorCode.INVALID_RECORDING_IDENTITY),
        ({"recorded_at": "2026-10-15T19:00:00"}, ValidationErrorCode.INVALID_RECORDED_AT),
        ({"content_sha256": "A" * 64}, ValidationErrorCode.INVALID_CONTENT_SHA256),
        ({"file_size_bytes": 0}, ValidationErrorCode.INVALID_FILE_SIZE),
        ({"duration_seconds": float("nan")}, ValidationErrorCode.INVALID_DURATION),
        ({"sample_rate": 12_345}, ValidationErrorCode.UNSUPPORTED_SAMPLE_RATE),
        ({"channels": 3}, ValidationErrorCode.UNSUPPORTED_CHANNEL_COUNT),
        ({"sample_format": "MP3"}, ValidationErrorCode.UNSUPPORTED_SAMPLE_FORMAT),
        ({"media_type": "audio/mpeg"}, ValidationErrorCode.UNSUPPORTED_MEDIA_TYPE),
    ],
)
def test_invalid_declaration_fields_fail_without_persistence(
    tmp_path: Path,
    changes: dict[str, object],
    code: ValidationErrorCode,
) -> None:
    connection, _ = open_database(tmp_path)
    with pytest.raises(IngestionDomainError) as raised:
        declare_recording(connection, declaration(**changes))
    assert raised.value.code is code
    assert connection.execute("SELECT COUNT(*) FROM server_recording_ingestions").fetchone()[0] == 0


def test_first_declaration_creates_only_one_awaiting_ingestion(tmp_path: Path) -> None:
    connection, _ = open_database(tmp_path)
    before = scientific_counts(connection)
    result = declare_recording(connection, declaration(), declared_at=NOW)
    assert result.outcome is IngestionOutcome.NEEDS_MEDIA
    assert result.state is IngestionState.AWAITING_MEDIA
    assert result.recording_id is None
    row = connection.execute("SELECT * FROM server_recording_ingestions").fetchone()
    assert row["recording_identity"] == RECORDING_IDENTITY
    assert row["state"] == "AWAITING_MEDIA"
    assert row["declaration_count"] == 1
    assert scientific_counts(connection) == before


def test_identical_lost_response_and_restart_retries_are_idempotent(tmp_path: Path) -> None:
    connection, database = open_database(tmp_path)
    first = declare_recording(connection, declaration(), declared_at=NOW)
    second = declare_recording(connection, declaration(), declared_at=SECOND)
    assert second.ingestion_id == first.ingestion_id
    assert second.outcome is IngestionOutcome.NEEDS_MEDIA
    connection.commit()
    connection.close()

    reopened = connect_database(database)
    third = declare_recording(reopened, declaration(), declared_at="2026-10-15T19:02:00+00:00")
    assert third.ingestion_id == first.ingestion_id
    row = reopened.execute("SELECT declaration_count FROM server_recording_ingestions").fetchone()
    assert row[0] == 3
    assert reopened.execute("SELECT COUNT(*) FROM recordings").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"content_sha256": "0" * 64}, ConflictReason.IMMUTABLE_CHECKSUM_MISMATCH),
        ({"recorded_at": SECOND}, ConflictReason.IMMUTABLE_RECORDED_AT_MISMATCH),
        ({"file_size_bytes": len(CONTENT) + 1}, ConflictReason.IMMUTABLE_SIZE_MISMATCH),
        ({"duration_seconds": 61.0}, ConflictReason.IMMUTABLE_DURATION_MISMATCH),
        ({"sample_rate": 44_100}, ConflictReason.IMMUTABLE_SAMPLE_RATE_MISMATCH),
        ({"channels": 2}, ConflictReason.IMMUTABLE_CHANNELS_MISMATCH),
    ],
)
def test_immutable_retry_conflicts_do_not_mutate_winner(
    tmp_path: Path,
    changes: dict[str, object],
    reason: ConflictReason,
) -> None:
    connection, _ = open_database(tmp_path)
    original = declaration()
    declare_recording(connection, original, declared_at=NOW)
    before = tuple(connection.execute("SELECT * FROM server_recording_ingestions").fetchone())
    result = declare_recording(connection, replace(original, **changes), declared_at=SECOND)
    assert result.outcome is IngestionOutcome.CONFLICT
    assert result.conflict_reason is reason
    after = tuple(connection.execute("SELECT * FROM server_recording_ingestions").fetchone())
    assert after == before


def test_station_sample_format_and_media_type_conflicts_are_structured(tmp_path: Path) -> None:
    connection, _ = open_database(tmp_path)
    connection.execute(
        """
        INSERT INTO stations (id, name, timezone, created_at, station_uuid)
        VALUES ('station-two', 'Station Two', 'UTC', ?, ?)
        """,
        (NOW, OTHER_STATION_UUID),
    )
    declare_recording(connection, declaration(), declared_at=NOW)
    station_conflict = declare_recording(
        connection,
        declaration(station_uuid=OTHER_STATION_UUID),
        declared_at=SECOND,
    )
    assert station_conflict.conflict_reason is ConflictReason.RECORDING_STATION_MISMATCH

    # Persistence-level immutable comparisons also protect future supported values.
    connection.execute("DROP TRIGGER server_recording_ingestions_declaration_immutable")
    connection.execute("UPDATE server_recording_ingestions SET sample_format = 'S24_LE'")
    sample_conflict = declare_recording(connection, declaration(), declared_at=SECOND)
    assert sample_conflict.conflict_reason is ConflictReason.IMMUTABLE_SAMPLE_FORMAT_MISMATCH
    connection.execute(
        "UPDATE server_recording_ingestions SET sample_format = 'S16_LE', media_type = 'audio/flac'"
    )
    media_conflict = declare_recording(connection, declaration(), declared_at=SECOND)
    assert media_conflict.conflict_reason is ConflictReason.IMMUTABLE_MEDIA_TYPE_MISMATCH


def test_different_identities_with_same_checksum_are_separate(tmp_path: Path) -> None:
    connection, _ = open_database(tmp_path)
    first = declare_recording(connection, declaration(), declared_at=NOW)
    second = declare_recording(
        connection,
        declaration(recording_identity=str(uuid.uuid4())),
        declared_at=SECOND,
    )
    assert first.ingestion_id != second.ingestion_id
    assert connection.execute("SELECT COUNT(*) FROM server_recording_ingestions").fetchone()[0] == 2


def test_available_verified_compatible_recording_is_already_present(tmp_path: Path) -> None:
    connection, _ = open_database(tmp_path)
    recording_id = add_existing_recording(connection, tmp_path)
    before = scientific_counts(connection)
    result = declare_recording(connection, declaration(), declared_at=NOW)
    assert result.outcome is IngestionOutcome.ALREADY_PRESENT
    assert result.state is IngestionState.COMPLETED
    assert result.recording_id == recording_id
    assert scientific_counts(connection) == before
    row = connection.execute(
        "SELECT state, completed_at FROM server_recording_ingestions"
    ).fetchone()
    assert tuple(row) == ("COMPLETED", NOW)


def test_available_historical_unknown_checksum_needs_media_without_backfill(
    tmp_path: Path,
) -> None:
    connection, _ = open_database(tmp_path)
    recording_id = add_existing_recording(connection, tmp_path, checksum=None)
    result = declare_recording(connection, declaration(), declared_at=NOW)
    assert result.outcome is IngestionOutcome.NEEDS_MEDIA
    assert result.recording_id == recording_id
    assert (
        connection.execute(
            "SELECT content_sha256 FROM recordings WHERE id = ?", (recording_id,)
        ).fetchone()[0]
        is None
    )


@pytest.mark.parametrize(
    "availability",
    [SourceAvailability.MISSING, SourceAvailability.INTENTIONALLY_EXPIRED],
)
def test_unavailable_existing_recording_needs_media_without_duplicate_or_provenance_change(
    tmp_path: Path,
    availability: SourceAvailability,
) -> None:
    connection, _ = open_database(tmp_path)
    recording_id = add_existing_recording(
        connection,
        tmp_path,
        availability=availability,
    )
    events_before = [
        tuple(row)
        for row in connection.execute(
            "SELECT * FROM recording_source_events WHERE recording_id = ? ORDER BY source_event_id",
            (recording_id,),
        )
    ]
    result = declare_recording(connection, declaration(), declared_at=NOW)
    assert result.outcome is IngestionOutcome.NEEDS_MEDIA
    assert result.recording_id == recording_id
    assert connection.execute("SELECT COUNT(*) FROM recordings").fetchone()[0] == 1
    assert [
        tuple(row)
        for row in connection.execute(
            "SELECT * FROM recording_source_events WHERE recording_id = ? ORDER BY source_event_id",
            (recording_id,),
        )
    ] == events_before


def test_existing_contradictory_recording_returns_conflict_without_ingestion(
    tmp_path: Path,
) -> None:
    connection, _ = open_database(tmp_path)
    add_existing_recording(connection, tmp_path, file_size_bytes=len(CONTENT) + 20)
    result = declare_recording(connection, declaration(), declared_at=NOW)
    assert result.outcome is IngestionOutcome.CONFLICT
    assert result.conflict_reason is ConflictReason.IMMUTABLE_SIZE_MISMATCH
    assert connection.execute("SELECT COUNT(*) FROM server_recording_ingestions").fetchone()[0] == 0


def test_completed_ingestion_stays_completed_if_media_later_disappears(tmp_path: Path) -> None:
    connection, _ = open_database(tmp_path)
    recording_id = add_existing_recording(connection, tmp_path)
    first = declare_recording(connection, declaration(), declared_at=NOW)
    assert first.state is IngestionState.COMPLETED
    set_source_availability(
        connection,
        recording_id=recording_id,
        availability=SourceAvailability.MISSING,
        reason_code="TEST_MEDIA_LOST",
        authorized_by="TEST",
        authorization_reference="server-ingestion-test",
        operation_id="server-ingestion-completed-source-lost",
        occurred_at=SECOND,
    )
    retry = declare_recording(connection, declaration(), declared_at=SECOND)
    assert retry.outcome is IngestionOutcome.NEEDS_MEDIA
    assert retry.state is IngestionState.COMPLETED


def test_operation_leaves_commit_control_to_caller(tmp_path: Path) -> None:
    connection, database = open_database(tmp_path)
    declare_recording(connection, declaration(), declared_at=NOW)
    assert connection.in_transaction
    observer = connect_database(database)
    assert observer.execute("SELECT COUNT(*) FROM server_recording_ingestions").fetchone()[0] == 0
    connection.commit()
    assert observer.execute("SELECT COUNT(*) FROM server_recording_ingestions").fetchone()[0] == 1


def test_forced_transaction_failure_leaves_no_partial_ingestion(tmp_path: Path) -> None:
    connection, _ = open_database(tmp_path)
    connection.execute(
        """
        CREATE TRIGGER test_ingestion_failure
        BEFORE INSERT ON server_recording_ingestions
        BEGIN
            SELECT RAISE(ABORT, 'forced ingestion failure');
        END
        """
    )
    with pytest.raises(IngestionPersistenceError, match="forced ingestion failure"):
        declare_recording(connection, declaration(), declared_at=NOW)
    assert connection.execute("SELECT COUNT(*) FROM server_recording_ingestions").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM recordings").fetchone()[0] == 0


def test_concurrent_identical_declarations_create_one_ingestion(tmp_path: Path) -> None:
    setup, database = open_database(tmp_path)
    setup.close()
    barrier = threading.Barrier(2)
    results: list[object] = []

    def worker() -> None:
        connection = connect_database(database)
        barrier.wait()
        try:
            results.append(declare_recording(connection, declaration(), declared_at=NOW))
            connection.commit()
        except Exception as error:  # pragma: no cover - assertion captures thread failure
            results.append(error)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert all(not thread.is_alive() for thread in threads)
    assert len(results) == 2
    assert all(
        getattr(result, "outcome", None) is IngestionOutcome.NEEDS_MEDIA for result in results
    )
    with connect_database(database) as connection:
        assert tuple(
            connection.execute(
                "SELECT COUNT(*), declaration_count FROM server_recording_ingestions"
            ).fetchone()
        ) == (1, 2)


def test_concurrent_conflicting_declarations_cannot_overwrite_winner(tmp_path: Path) -> None:
    setup, database = open_database(tmp_path)
    setup.close()
    barrier = threading.Barrier(2)
    candidates = (declaration(), declaration(content_sha256="0" * 64))
    results: list[object] = []

    def worker(candidate: RecordingDeclaration) -> None:
        connection = connect_database(database)
        barrier.wait()
        try:
            results.append(declare_recording(connection, candidate, declared_at=NOW))
            connection.commit()
        except Exception as error:  # pragma: no cover - assertion captures thread failure
            results.append(error)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(candidate,)) for candidate in candidates]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    outcomes = {getattr(result, "outcome", None) for result in results}
    assert outcomes == {IngestionOutcome.NEEDS_MEDIA, IngestionOutcome.CONFLICT}
    with connect_database(database) as connection:
        row = connection.execute(
            "SELECT COUNT(*), content_sha256, declaration_count FROM server_recording_ingestions"
        ).fetchone()
        assert row[0] == 1
        assert row[1] in {CHECKSUM, "0" * 64}
        assert row[2] == 1


def test_observability_reports_counts_oldest_pending_and_station_activity(
    tmp_path: Path,
) -> None:
    connection, _ = open_database(tmp_path)
    declare_recording(connection, declaration(), declared_at=NOW)
    declare_recording(connection, declaration(), declared_at=SECOND)
    existing_identity = str(uuid.uuid4())
    add_existing_recording(connection, tmp_path, identity=existing_identity)
    declare_recording(
        connection,
        declaration(recording_identity=existing_identity),
        declared_at=SECOND,
    )
    summary = ingestion_summary(connection)
    assert summary.total == 2
    assert summary.awaiting_media == 1
    assert summary.completed == 1
    assert summary.oldest_pending_at == NOW
    assert summary.repeat_declarations == 1
    activity = last_declarations_by_station(connection)
    assert len(activity) == 1
    assert activity[0].station_uuid == STATION_UUID
    assert activity[0].ingestion_count == 2
    assert activity[0].declaration_count == 3


def test_ingestion_constraints_protect_history_and_mapping(tmp_path: Path) -> None:
    connection, _ = open_database(tmp_path)
    declare_recording(connection, declaration(), declared_at=NOW)
    with pytest.raises(sqlite3.IntegrityError, match="declaration is immutable"):
        connection.execute(
            "UPDATE server_recording_ingestions SET content_sha256 = ?",
            ("0" * 64,),
        )
    with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
        connection.execute("DELETE FROM server_recording_ingestions")
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
