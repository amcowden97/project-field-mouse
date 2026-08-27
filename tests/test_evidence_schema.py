from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from app.database.connection import insert_recording
from app.migrations import MIGRATIONS_DIRECTORY, migrate
from app.science import ScienceInvariantError
from app.science.evidence import (
    EvidenceFamily,
    EvidenceLineageInput,
    EvidenceSourceInput,
    EvidenceStance,
    SourceRole,
    append_evidence,
)
from app.science.protections import (
    ProtectionOrigin,
    ProtectionType,
    add_recording_protection,
    release_recording_protection,
)
from app.science.recordings import (
    SourceAvailability,
    set_source_availability,
    source_availability,
)


NOW = "2026-08-26T20:00:00+00:00"


def open_database(tmp_path: Path) -> tuple[sqlite3.Connection, Path, int, int]:
    database = tmp_path / "fieldmouse.db"
    migrate(database, tmp_path / "backups")
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        "INSERT INTO stations (id, name, timezone, created_at) VALUES (?, ?, ?, ?)",
        ("station-one", "Station", "UTC", NOW),
    )
    audio = tmp_path / "recording.wav"
    audio.write_bytes(b"RIFF" + b"audio" * 100)
    recording_id = insert_recording(
        connection,
        station_id="station-one",
        file_path=audio,
        recorded_at=NOW,
        duration_seconds=60,
        sample_rate=48000,
        channels=1,
        sample_format="S16_LE",
        file_size_bytes=audio.stat().st_size,
    )
    detection_id = int(
        connection.execute(
            """
            INSERT INTO detections (
                recording_id, detector, common_name, scientific_name,
                confidence, start_time, end_time, created_at
            ) VALUES (?, 'birdnet', 'American Robin', 'Turdus migratorius',
                      0.91, 1.0, 4.0, ?)
            """,
            (recording_id, NOW),
        ).lastrowid
    )
    connection.commit()
    return connection, audio, recording_id, detection_id


def model_evidence(
    connection: sqlite3.Connection,
    *,
    detection_id: int,
    key: str,
    sources: tuple[EvidenceSourceInput, ...] = (),
    family: EvidenceFamily = EvidenceFamily.MODEL,
    evidence_type: str = "MODEL_PREDICTION",
    lineage: tuple[EvidenceLineageInput, ...] = (),
) -> int:
    return append_evidence(
        connection,
        detection_id=detection_id,
        family=family,
        evidence_type=evidence_type,
        stance=EvidenceStance.SUPPORTS,
        source_type="DETECTOR",
        source_id="birdnet",
        source_version="0.2.16",
        algorithm_version="model-v1",
        confidence_value=0.91,
        confidence_semantics="BirdNET classifier score",
        reason_code="MODEL_OUTPUT",
        reasoning="BirdNET emitted this taxon claim.",
        observed_at=NOW,
        idempotency_key=key,
        claimed_scientific_name="Turdus migratorius",
        claimed_common_name="American Robin",
        sources=sources,
        lineage=lineage,
    )


def test_fresh_database_has_foundation_and_stable_identity(tmp_path: Path) -> None:
    connection, _, recording_id, _ = open_database(tmp_path)
    row = connection.execute(
        "SELECT recording_identity, source_availability, media_type FROM recordings"
    ).fetchone()
    assert row["recording_identity"] == f"station-one:{recording_id:020d}"
    assert row["source_availability"] == "AVAILABLE"
    assert row["media_type"] == "audio/wav"
    with pytest.raises(sqlite3.IntegrityError, match="identity is immutable"):
        connection.execute(
            "UPDATE recordings SET recording_identity = 'replacement' WHERE id = ?",
            (recording_id,),
        )


def test_v11_migration_backfills_available_expired_and_missing(tmp_path: Path) -> None:
    old_migrations = tmp_path / "old-migrations"
    old_migrations.mkdir()
    for source in sorted(MIGRATIONS_DIRECTORY.glob("000[1-5]_*.sql")):
        shutil.copy2(source, old_migrations / source.name)
    database = tmp_path / "legacy.db"
    migrate(database, tmp_path / "backups", old_migrations)
    present = tmp_path / "present.wav"
    present.write_bytes(b"audio")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO stations (id, name, timezone, created_at) VALUES ('s', 'S', 'UTC', ?)",
            (NOW,),
        )
        rows = (
            (101, str(present), "processed"),
            (102, str(tmp_path / "expired.wav"), "audio_expired"),
            (103, str(tmp_path / "unexplained.wav"), "processed"),
        )
        for recording_id, path, status in rows:
            connection.execute(
                """
                INSERT INTO recordings (
                    id, station_id, file_path, recorded_at, duration_seconds,
                    sample_rate, channels, sample_format, file_size_bytes,
                    processing_status, created_at
                ) VALUES (?, 's', ?, ?, 60, 48000, 1, 'S16_LE', 5, ?, ?)
                """,
                (recording_id, path, NOW, status, NOW),
            )
        connection.execute(
            """
            INSERT INTO detections (
                id, recording_id, detector, common_name, scientific_name,
                confidence, start_time, end_time, created_at
            ) VALUES (201, 102, 'birdnet', 'Robin', 'Turdus migratorius',
                      0.8, 0, 3, ?)
            """,
            (NOW,),
        )
        connection.commit()
    migrate(database, tmp_path / "backups")
    with sqlite3.connect(database) as connection:
        states = dict(connection.execute("SELECT id, source_availability FROM recordings"))
        report = connection.execute(
            """
            SELECT available_count, intentionally_expired_count, missing_count,
                   confident_expiration_count, ambiguous_absent_count
            FROM evidence_schema_migration_runs
            """
        ).fetchone()
        assert states == {101: "AVAILABLE", 102: "INTENTIONALLY_EXPIRED", 103: "MISSING"}
        assert report == (1, 1, 1, 1, 1)
        assert connection.execute("SELECT COUNT(*) FROM recordings").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM detections").fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_intentional_expiration_requires_provenance_and_retains_path(tmp_path: Path) -> None:
    connection, audio, recording_id, _ = open_database(tmp_path)
    with pytest.raises(sqlite3.IntegrityError, match="requires provenance"):
        connection.execute(
            "UPDATE recordings SET source_availability = 'INTENTIONALLY_EXPIRED' WHERE id = ?",
            (recording_id,),
        )
    set_source_availability(
        connection,
        recording_id=recording_id,
        availability=SourceAvailability.INTENTIONALLY_EXPIRED,
        reason_code="AUTHORIZED_RETENTION",
        authorized_by="operator",
        authorization_reference="cleanup-run-1",
        operation_id="expire-one",
    )
    row = connection.execute(
        "SELECT file_path, source_availability FROM recordings WHERE id = ?",
        (recording_id,),
    ).fetchone()
    assert row["file_path"] == str(audio)
    assert row["source_availability"] == "INTENTIONALLY_EXPIRED"
    assert audio.is_file()


def test_missing_and_expired_are_distinct_and_path_is_not_availability(tmp_path: Path) -> None:
    connection, audio, recording_id, _ = open_database(tmp_path)
    set_source_availability(
        connection,
        recording_id=recording_id,
        availability=SourceAvailability.MISSING,
        reason_code="SOURCE_CHECK_FAILED",
        authorized_by="auditor",
        authorization_reference="audit-1",
        operation_id="missing-one",
    )
    assert audio.is_file()
    assert source_availability(connection, recording_id) is SourceAvailability.MISSING


def test_restoration_preserves_expiration_history(tmp_path: Path) -> None:
    connection, _, recording_id, _ = open_database(tmp_path)
    set_source_availability(
        connection,
        recording_id=recording_id,
        availability=SourceAvailability.INTENTIONALLY_EXPIRED,
        reason_code="AUTHORIZED_RETENTION",
        authorized_by="operator",
        authorization_reference="cleanup-run-2",
        operation_id="expire-two",
    )
    set_source_availability(
        connection,
        recording_id=recording_id,
        availability=SourceAvailability.AVAILABLE,
        reason_code="SOURCE_RESTORED",
        authorized_by="operator",
        authorization_reference="restore-1",
        operation_id="restore-one",
    )
    history = connection.execute(
        """
        SELECT to_availability FROM recording_source_events
        WHERE recording_id = ? ORDER BY source_event_id
        """,
        (recording_id,),
    ).fetchall()
    assert source_availability(connection, recording_id) is SourceAvailability.AVAILABLE
    assert [row[0] for row in history][-2:] == ["INTENTIONALLY_EXPIRED", "AVAILABLE"]

    with pytest.raises(sqlite3.IntegrityError, match="requires provenance"):
        connection.execute(
            "UPDATE recordings SET source_availability = 'INTENTIONALLY_EXPIRED' WHERE id = ?",
            (recording_id,),
        )


def test_evidence_supports_one_multiple_and_shared_recording_sources(tmp_path: Path) -> None:
    connection, _, recording_id, detection_id = open_database(tmp_path)
    second_audio = tmp_path / "second.wav"
    second_audio.write_bytes(b"audio")
    second_recording = insert_recording(
        connection,
        station_id="station-one",
        file_path=second_audio,
        recorded_at=NOW,
        duration_seconds=30,
        sample_rate=48000,
        channels=1,
        sample_format="S16_LE",
        file_size_bytes=5,
    )
    first = model_evidence(
        connection,
        detection_id=detection_id,
        key="evidence-one",
        sources=(EvidenceSourceInput(recording_id, SourceRole.PRIMARY),),
    )
    second = model_evidence(
        connection,
        detection_id=detection_id,
        key="evidence-two",
        sources=(
            EvidenceSourceInput(recording_id, SourceRole.PRIMARY, 1.0, 5.0),
            EvidenceSourceInput(second_recording, SourceRole.CONTEXT),
        ),
    )
    assert connection.execute(
        "SELECT COUNT(*) FROM evidence_sources WHERE evidence_id = ?", (first,)
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM evidence_sources WHERE evidence_id = ?", (second,)
    ).fetchone()[0] == 2
    assert connection.execute(
        "SELECT COUNT(DISTINCT evidence_id) FROM evidence_sources WHERE recording_id = ?",
        (recording_id,),
    ).fetchone()[0] == 2


@pytest.mark.parametrize(
    ("start", "end"),
    ((-1.0, 2.0), (2.0, 2.0), (4.0, 3.0), (1.0, 61.0), (None, 2.0)),
)
def test_invalid_evidence_source_offsets_are_rejected(
    tmp_path: Path, start: float | None, end: float | None
) -> None:
    connection, _, recording_id, detection_id = open_database(tmp_path)
    with pytest.raises(ScienceInvariantError, match="interval"):
        model_evidence(
            connection,
            detection_id=detection_id,
            key=f"invalid-{start}-{end}",
            sources=(EvidenceSourceInput(recording_id, SourceRole.PRIMARY, start, end),),
        )


def test_evidence_survives_source_expiration_and_has_no_availability_copy(tmp_path: Path) -> None:
    connection, _, recording_id, detection_id = open_database(tmp_path)
    evidence_id = model_evidence(
        connection,
        detection_id=detection_id,
        key="survives-expiry",
        sources=(EvidenceSourceInput(recording_id, SourceRole.PRIMARY),),
    )
    set_source_availability(
        connection,
        recording_id=recording_id,
        availability=SourceAvailability.INTENTIONALLY_EXPIRED,
        reason_code="AUTHORIZED_RETENTION",
        authorized_by="operator",
        authorization_reference="cleanup-run-3",
        operation_id="expire-three",
    )
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(evidence_sources)")
    }
    assert "source_availability" not in columns
    assert connection.execute(
        "SELECT COUNT(*) FROM evidence WHERE evidence_id = ?", (evidence_id,)
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM detections WHERE id = ?", (detection_id,)
    ).fetchone()[0] == 1


def test_automated_human_evidence_and_unparented_derived_evidence_are_rejected(
    tmp_path: Path,
) -> None:
    connection, _, _, detection_id = open_database(tmp_path)
    with pytest.raises(ScienceInvariantError, match="Review system"):
        model_evidence(
            connection,
            detection_id=detection_id,
            key="fake-human",
            family=EvidenceFamily.HUMAN,
            evidence_type="HUMAN_CONFIRMATION",
        )
    with pytest.raises(ScienceInvariantError, match="lineage"):
        model_evidence(
            connection,
            detection_id=detection_id,
            key="unparented-derived",
            family=EvidenceFamily.DERIVED,
            evidence_type="DERIVED_ASSERTION",
        )


def test_evidence_is_append_only_and_lineage_rejects_cycles(tmp_path: Path) -> None:
    connection, _, _, detection_id = open_database(tmp_path)
    parent = model_evidence(connection, detection_id=detection_id, key="parent")
    child = model_evidence(
        connection,
        detection_id=detection_id,
        key="child",
        family=EvidenceFamily.DERIVED,
        evidence_type="DERIVED_ASSERTION",
        lineage=(EvidenceLineageInput(parent),),
    )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(
            "UPDATE evidence SET reasoning = 'rewrite' WHERE evidence_id = ?", (parent,)
        )
    with pytest.raises(sqlite3.IntegrityError, match="cycle"):
        connection.execute(
            """
            INSERT INTO evidence_lineage (
                child_evidence_id, parent_evidence_id, relationship, created_at
            ) VALUES (?, ?, 'DERIVED_FROM', ?)
            """,
            (parent, child, NOW),
        )


def test_multiple_protections_release_independently_and_keep_history(tmp_path: Path) -> None:
    connection, _, recording_id, _ = open_database(tmp_path)
    manual = add_recording_protection(
        connection,
        recording_id=recording_id,
        protection_type=ProtectionType.MANUALLY_PINNED,
        origin_type=ProtectionOrigin.MANUAL,
        origin_reference="pin-request-1",
        reason_code="OPERATOR_PIN",
        reason="Operator retained this recording.",
        created_by="operator",
    )
    research = add_recording_protection(
        connection,
        recording_id=recording_id,
        protection_type=ProtectionType.RESEARCH_HOLD,
        origin_type=ProtectionOrigin.RESEARCH,
        origin_reference="research-project-1",
        reason_code="ACTIVE_RESEARCH",
        reason="Recording is part of active research.",
        created_by="researcher",
    )
    release_recording_protection(
        connection,
        protection_id=manual,
        released_by="operator",
        release_reason="Manual pin no longer required.",
    )
    rows = connection.execute(
        "SELECT protection_id, released_at FROM recording_protections ORDER BY protection_id"
    ).fetchall()
    assert rows[0][0] == manual and rows[0][1] is not None
    assert rows[1][0] == research and rows[1][1] is None
    assert connection.execute("SELECT COUNT(*) FROM recording_protections").fetchone()[0] == 2


def test_manual_pin_blocks_expiration_until_released(tmp_path: Path) -> None:
    connection, _, recording_id, _ = open_database(tmp_path)
    protection_id = add_recording_protection(
        connection,
        recording_id=recording_id,
        protection_type=ProtectionType.MANUALLY_PINNED,
        origin_type=ProtectionOrigin.MANUAL,
        origin_reference="pin-request-2",
        reason_code="OPERATOR_PIN",
        reason="Retain indefinitely until explicit release.",
        created_by="operator",
    )
    with pytest.raises(ScienceInvariantError, match="blocks expiration"):
        set_source_availability(
            connection,
            recording_id=recording_id,
            availability=SourceAvailability.INTENTIONALLY_EXPIRED,
            reason_code="AUTHORIZED_RETENTION",
            authorized_by="cleanup",
            authorization_reference="cleanup-1",
            operation_id="blocked-expiry",
        )
    release_recording_protection(
        connection,
        protection_id=protection_id,
        released_by="operator",
        release_reason="Release approved.",
    )
    set_source_availability(
        connection,
        recording_id=recording_id,
        availability=SourceAvailability.INTENTIONALLY_EXPIRED,
        reason_code="AUTHORIZED_RETENTION",
        authorized_by="cleanup",
        authorization_reference="cleanup-2",
        operation_id="allowed-expiry",
    )
    assert source_availability(connection, recording_id) is SourceAvailability.INTENTIONALLY_EXPIRED


def test_duplicate_active_protection_and_invalid_origin_are_rejected(tmp_path: Path) -> None:
    connection, _, recording_id, _ = open_database(tmp_path)
    arguments = dict(
        recording_id=recording_id,
        protection_type=ProtectionType.MANUALLY_PINNED,
        origin_type=ProtectionOrigin.MANUAL,
        origin_reference="pin-request-3",
        reason_code="OPERATOR_PIN",
        reason="Retain.",
        created_by="operator",
    )
    add_recording_protection(connection, **arguments)
    with pytest.raises(ScienceInvariantError):
        add_recording_protection(connection, **arguments)
    with pytest.raises(ScienceInvariantError, match="requires an Evidence ID"):
        add_recording_protection(
            connection,
            recording_id=recording_id,
            protection_type=ProtectionType.VERIFICATION_EVIDENCE,
            origin_type=ProtectionOrigin.EVIDENCE,
            origin_reference="evidence-missing",
            reason_code="EVIDENCE_HOLD",
            reason="Evidence source.",
            created_by="system",
        )


def test_scientific_metadata_survives_lifecycle_changes(tmp_path: Path) -> None:
    connection, _, recording_id, detection_id = open_database(tmp_path)
    evidence_id = model_evidence(
        connection,
        detection_id=detection_id,
        key="science-survives",
        sources=(EvidenceSourceInput(recording_id, SourceRole.PRIMARY),),
    )
    set_source_availability(
        connection,
        recording_id=recording_id,
        availability=SourceAvailability.MISSING,
        reason_code="SOURCE_UNREACHABLE",
        authorized_by="auditor",
        authorization_reference="audit-2",
        operation_id="missing-science",
    )
    assert connection.execute("SELECT COUNT(*) FROM recordings").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM detections").fetchone()[0] == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM evidence WHERE evidence_id = ?", (evidence_id,)
    ).fetchone()[0] == 1
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
