from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from app.database.connection import insert_recording
from app.migrations import MIGRATIONS_DIRECTORY, migrate
from app.science import ScienceInvariantError
from app.science.assessments import (
    AssessmentResult,
    create_assessment,
    get_assessment,
    get_assessment_evidence,
    list_assessment_history,
    list_current_assessments,
)
from app.science.evidence import (
    EvidenceFamily,
    EvidenceSourceInput,
    EvidenceStance,
    SourceRole,
    append_evidence,
)
from app.science.recordings import SourceAvailability, set_source_availability
from app.science.reviews import (
    ReviewDecision,
    ReviewEvidenceInput,
    ReviewEvidenceRole,
    ReviewerRole,
    create_review,
)
from app.verification.reviews import ReviewInput, record_review


NOW = "2026-09-05T18:00:00+00:00"


def open_database(
    tmp_path: Path,
) -> tuple[sqlite3.Connection, Path, int, int, int]:
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
    first_detection = insert_detection(
        connection, recording_id, "Turdus migratorius", "American Robin"
    )
    second_detection = insert_detection(
        connection, recording_id, "Cardinalis cardinalis", "Northern Cardinal"
    )
    connection.commit()
    return connection, audio, recording_id, first_detection, second_detection


def insert_detection(
    connection: sqlite3.Connection,
    recording_id: int,
    scientific_name: str,
    common_name: str,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO detections (
            recording_id, detector, common_name, scientific_name,
            confidence, start_time, end_time, created_at
        ) VALUES (?, 'birdnet', ?, ?, 0.91, 1.0, 4.0, ?)
        """,
        (recording_id, common_name, scientific_name, NOW),
    )
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def add_model_evidence(
    connection: sqlite3.Connection,
    detection_id: int,
    key: str,
    *,
    recording_id: int | None = None,
) -> int:
    sources = (
        (EvidenceSourceInput(recording_id, SourceRole.PRIMARY),) if recording_id is not None else ()
    )
    return append_evidence(
        connection,
        detection_id=detection_id,
        family=EvidenceFamily.MODEL,
        evidence_type="MODEL_PREDICTION",
        stance=EvidenceStance.SUPPORTS,
        source_type="DETECTOR",
        source_id="birdnet",
        source_version="0.2.16",
        algorithm_version="model-v1",
        confidence_value=0.91,
        confidence_semantics="BirdNET classifier score",
        reason_code="MODEL_OUTPUT",
        reasoning="BirdNET emitted this historical claim.",
        observed_at=NOW,
        idempotency_key=key,
        claimed_scientific_name="Turdus migratorius",
        claimed_common_name="American Robin",
        sources=sources,
    )


def add_human_evidence(
    connection: sqlite3.Connection,
    detection_id: int,
    key: str,
) -> int:
    """Represent trusted Review-owned Evidence without using the automated writer."""
    cursor = connection.execute(
        """
        INSERT INTO evidence (
            evidence_identity, detection_id, family, evidence_type, stance,
            claimed_scientific_name, claimed_common_name, source_type,
            source_id, source_version, reason_code, reasoning, metadata_json,
            reviewer_id, reviewer_role, observed_at, created_at, idempotency_key
        ) VALUES (?, ?, 'HUMAN', 'HUMAN_CONFIRMATION', 'SUPPORTS',
                  'Turdus migratorius', 'American Robin', 'HUMAN_REVIEW',
                  'reviewer-one', '1', 'HUMAN_CONFIRMATION',
                  'A human reviewed the cited evidence.', '{}',
                  'reviewer-one', 'HUMAN', ?, ?, ?)
        """,
        (f"human-evidence:{key}", detection_id, NOW, NOW, key),
    )
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def add_assessment(
    connection: sqlite3.Connection,
    detection_id: int,
    evidence_ids: tuple[int, ...],
    *,
    result: AssessmentResult = AssessmentResult.SUPPORTED,
    key: str = "assessment-one",
    supersedes: int | None = None,
    alternate_scientific_name: str | None = None,
    alternate_common_name: str | None = None,
) -> int:
    return create_assessment(
        connection,
        detection_id=detection_id,
        result=result,
        evidence_ids=evidence_ids,
        reason_code="EXPLICIT_TEST_CONCLUSION",
        reasoning="An explicit test operator recorded this conclusion.",
        created_by="test-operator",
        idempotency_key=key,
        supersedes_assessment_id=supersedes,
        alternate_scientific_name=alternate_scientific_name,
        alternate_common_name=alternate_common_name,
    )


def test_fresh_schema_has_constraints_indexes_and_no_confidence(tmp_path: Path) -> None:
    connection, _, _, detection_id, _ = open_database(tmp_path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(assessments)")}
    indexes = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
    }
    assert "confidence" not in columns
    assert "review_id" not in columns
    assert {
        "idx_assessments_detection_history",
        "idx_assessments_result_history",
        "idx_assessments_assessed_taxon",
        "idx_assessments_supersedes",
        "idx_assessment_evidence_assessment",
        "idx_assessment_evidence_evidence",
    } <= indexes
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO assessments (
                assessment_identity, detection_id, result,
                assessed_scientific_name, assessed_common_name, reason_code,
                reasoning, created_by, input_fingerprint, idempotency_key, created_at
            ) VALUES ('bad-result', ?, 'CONFIRM', 'Turdus migratorius',
                      'American Robin', 'TEST', 'Invalid result.', 'tester', ?,
                      'bad-result', ?)
            """,
            (detection_id, "a" * 64, NOW),
        )
    evidence_id = add_model_evidence(connection, detection_id, "invalid-result")
    with pytest.raises(ScienceInvariantError, match="Unknown Assessment result"):
        create_assessment(
            connection,
            detection_id=detection_id,
            result="CONFIRM",
            evidence_ids=(evidence_id,),
            reason_code="TEST",
            reasoning="Invalid Review-domain result.",
            created_by="tester",
            idempotency_key="invalid-assessment-result",
        )


@pytest.mark.parametrize(
    "result",
    [
        AssessmentResult.SUPPORTED,
        AssessmentResult.NOT_SUPPORTED,
        AssessmentResult.INCONCLUSIVE,
    ],
)
def test_standard_assessment_results_preserve_detection(
    tmp_path: Path,
    result: AssessmentResult,
) -> None:
    connection, _, _, detection_id, _ = open_database(tmp_path)
    evidence_id = add_model_evidence(connection, detection_id, f"result-{result.value}")
    before = tuple(
        connection.execute("SELECT * FROM detections WHERE id = ?", (detection_id,)).fetchone()
    )
    assessment_id = add_assessment(
        connection,
        detection_id,
        (evidence_id,),
        result=result,
        key=f"assessment-{result.value}",
    )
    assessment = get_assessment(connection, assessment_id)
    assert assessment is not None
    assert assessment.result == result.value
    assert assessment.assessed_scientific_name == "Turdus migratorius"
    assert assessment.assessed_common_name == "American Robin"
    after = tuple(
        connection.execute("SELECT * FROM detections WHERE id = ?", (detection_id,)).fetchone()
    )
    assert after == before


def test_alternate_taxon_requires_claim_and_preserves_machine_taxon(tmp_path: Path) -> None:
    connection, _, _, detection_id, _ = open_database(tmp_path)
    evidence_id = add_model_evidence(connection, detection_id, "alternate-taxon")
    assessment_id = add_assessment(
        connection,
        detection_id,
        (evidence_id,),
        result=AssessmentResult.ALTERNATE_TAXON,
        key="alternate-assessment",
        alternate_scientific_name="Ixoreus naevius",
        alternate_common_name="Varied Thrush",
    )
    assessment = get_assessment(connection, assessment_id)
    assert assessment is not None
    assert assessment.alternate_scientific_name == "Ixoreus naevius"
    detection = connection.execute(
        "SELECT scientific_name, common_name FROM detections WHERE id = ?",
        (detection_id,),
    ).fetchone()
    assert tuple(detection) == ("Turdus migratorius", "American Robin")
    with pytest.raises(ScienceInvariantError, match="alternate taxon"):
        add_assessment(
            connection,
            detection_id,
            (evidence_id,),
            result=AssessmentResult.ALTERNATE_TAXON,
            key="missing-alternate",
        )


def test_many_to_many_evidence_and_idempotent_retry(tmp_path: Path) -> None:
    connection, _, _, detection_id, _ = open_database(tmp_path)
    first = add_model_evidence(connection, detection_id, "many-first")
    second = add_model_evidence(connection, detection_id, "many-second")
    assessment_id = add_assessment(connection, detection_id, (second, first), key="many-assessment")
    retry_id = add_assessment(connection, detection_id, (first, second), key="many-assessment")
    historical_id = add_assessment(
        connection,
        detection_id,
        (first,),
        result=AssessmentResult.INCONCLUSIVE,
        key="historical-assessment",
    )
    assert retry_id == assessment_id
    assert [item.evidence_id for item in get_assessment_evidence(connection, assessment_id)] == [
        first,
        second,
    ]
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM assessment_evidence WHERE evidence_id = ?", (first,)
        ).fetchone()[0]
        == 2
    )
    assert historical_id != assessment_id
    assert connection.execute("SELECT COUNT(*) FROM assessments").fetchone()[0] == 2
    with pytest.raises(ScienceInvariantError, match="different inputs"):
        add_assessment(
            connection,
            detection_id,
            (first,),
            result=AssessmentResult.NOT_SUPPORTED,
            key="many-assessment",
        )


def test_missing_duplicate_and_unrelated_evidence_are_rejected(tmp_path: Path) -> None:
    connection, _, _, detection_id, other_detection = open_database(tmp_path)
    evidence_id = add_model_evidence(connection, detection_id, "valid-evidence")
    unrelated = add_model_evidence(connection, other_detection, "unrelated-evidence")
    with pytest.raises(ScienceInvariantError, match="at least one Evidence"):
        add_assessment(connection, detection_id, (), key="no-evidence")
    with pytest.raises(ScienceInvariantError, match="Unknown Evidence"):
        add_assessment(connection, detection_id, (999999,), key="missing-evidence")
    with pytest.raises(ScienceInvariantError, match="assessed Detection"):
        add_assessment(connection, detection_id, (unrelated,), key="unrelated")
    with pytest.raises(ScienceInvariantError, match="Duplicate"):
        add_assessment(connection, detection_id, (evidence_id, evidence_id), key="duplicate")
    with pytest.raises(ScienceInvariantError, match="Unknown Detection"):
        add_assessment(connection, 999999, (evidence_id,), key="missing-detection")


def test_assessment_write_is_atomic_on_relationship_failure(tmp_path: Path) -> None:
    connection, _, _, detection_id, _ = open_database(tmp_path)
    first = add_model_evidence(connection, detection_id, "atomic-first")
    second = add_model_evidence(connection, detection_id, "atomic-second")
    connection.execute(
        f"""
        CREATE TRIGGER force_assessment_link_failure
        BEFORE INSERT ON assessment_evidence
        WHEN NEW.evidence_id = {second}
        BEGIN
            SELECT RAISE(ABORT, 'forced assessment evidence failure');
        END
        """
    )
    with pytest.raises(ScienceInvariantError, match="forced assessment evidence failure"):
        add_assessment(connection, detection_id, (first, second), key="atomic-failure")
    assert connection.execute("SELECT COUNT(*) FROM assessments").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM assessment_evidence").fetchone()[0] == 0


def test_assessment_and_relationships_are_append_only(tmp_path: Path) -> None:
    connection, _, _, detection_id, _ = open_database(tmp_path)
    evidence_id = add_model_evidence(connection, detection_id, "append-only")
    assessment_id = add_assessment(connection, detection_id, (evidence_id,), key="append-only")
    link_id = get_assessment_evidence(connection, assessment_id)[0].assessment_evidence_id
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(
            "UPDATE assessments SET result = 'INCONCLUSIVE' WHERE assessment_id = ?",
            (assessment_id,),
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute("DELETE FROM assessments WHERE assessment_id = ?", (assessment_id,))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(
            "UPDATE assessment_evidence SET evidence_id = ? WHERE assessment_evidence_id = ?",
            (evidence_id, link_id),
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(
            "DELETE FROM assessment_evidence WHERE assessment_evidence_id = ?",
            (link_id,),
        )


def test_supersession_preserves_history_and_derives_current_head(tmp_path: Path) -> None:
    connection, _, _, detection_id, other_detection = open_database(tmp_path)
    evidence_id = add_model_evidence(connection, detection_id, "supersession")
    first = add_assessment(connection, detection_id, (evidence_id,), key="superseded")
    second = add_assessment(
        connection,
        detection_id,
        (evidence_id,),
        result=AssessmentResult.INCONCLUSIVE,
        key="replacement",
        supersedes=first,
    )
    assert [item.assessment_id for item in list_assessment_history(connection, detection_id)] == [
        first,
        second,
    ]
    assert [item.assessment_id for item in list_current_assessments(connection, detection_id)] == [
        second
    ]
    other_evidence = add_model_evidence(connection, other_detection, "other-assessment")
    with pytest.raises(ScienceInvariantError, match="within one Detection"):
        add_assessment(
            connection,
            other_detection,
            (other_evidence,),
            key="cross-detection",
            supersedes=first,
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO assessments (
                assessment_id, assessment_identity, detection_id, result,
                assessed_scientific_name, assessed_common_name, reason_code,
                reasoning, created_by, supersedes_assessment_id,
                input_fingerprint, idempotency_key, created_at
            ) VALUES (999, 'self-assessment', ?, 'SUPPORTED',
                      'Turdus migratorius', 'American Robin', 'TEST',
                      'Self reference.', 'tester', 999, ?, 'self-assessment', ?)
            """,
            (detection_id, "b" * 64, NOW),
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(
            "UPDATE assessments SET supersedes_assessment_id = ? WHERE assessment_id = ?",
            (second, first),
        )


def test_human_review_is_independent_and_does_not_create_assessment(tmp_path: Path) -> None:
    connection, _, _, detection_id, _ = open_database(tmp_path)
    evidence_id = add_human_evidence(connection, detection_id, "human-review-evidence")
    review_id = create_review(
        connection,
        detection_id=detection_id,
        decision=ReviewDecision.CONFIRM,
        reviewer_identity="reviewer-one",
        reviewer_role=ReviewerRole.USER,
        reviewed_at=NOW,
        reason_code="HUMAN_CONFIRMATION",
        evidence=(ReviewEvidenceInput(evidence_id, ReviewEvidenceRole.PRIMARY),),
    )
    assert review_id > 0
    assert connection.execute("SELECT COUNT(*) FROM assessments").fetchone()[0] == 0
    assessment_id = add_assessment(
        connection, detection_id, (evidence_id,), key="explicit-human-assessment"
    )
    assert assessment_id > 0
    assert connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM review_evidence").fetchone()[0] == 1


def test_legacy_truth_looking_states_do_not_create_assessments(tmp_path: Path) -> None:
    connection, _, _, detection_id, _ = open_database(tmp_path)
    connection.execute(
        """
        INSERT INTO verifications (
            detection_id, consensus_score, status, reason, explanation_json,
            rule_action, rule_name, review_status, created_at, updated_at,
            evidence_json, review_priority, review_flags_json
        ) VALUES (?, 0.99, 'verified', 'legacy', '{}', 'accept', 'legacy-rule',
                  'confirmed', ?, ?, '[]', 0, '[]')
        """,
        (detection_id, NOW, NOW),
    )
    record_review(
        connection,
        ReviewInput(
            detection_id,
            "corrected_species",
            "legacy-reviewer",
            corrected_common_name="Varied Thrush",
        ),
    )
    record_review(
        connection,
        ReviewInput(detection_id, "rejected", "legacy-reviewer"),
    )
    create_review_evidence = add_model_evidence(connection, detection_id, "review-confirm")
    create_review(
        connection,
        detection_id=detection_id,
        decision=ReviewDecision.CONFIRM,
        reviewer_identity="reviewer-one",
        reviewer_role=ReviewerRole.USER,
        reviewed_at=NOW,
        reason_code="CONFIRM",
        evidence=(ReviewEvidenceInput(create_review_evidence, ReviewEvidenceRole.PRIMARY),),
    )
    assert connection.execute("SELECT COUNT(*) FROM assessments").fetchone()[0] == 0


@pytest.mark.parametrize(
    "availability",
    [SourceAvailability.INTENTIONALLY_EXPIRED, SourceAvailability.MISSING],
)
def test_source_lifecycle_preserves_assessment_provenance(
    tmp_path: Path,
    availability: SourceAvailability,
) -> None:
    connection, _, recording_id, detection_id, _ = open_database(tmp_path)
    evidence_id = add_model_evidence(
        connection,
        detection_id,
        f"lifecycle-{availability.value}",
        recording_id=recording_id,
    )
    assessment_id = add_assessment(
        connection,
        detection_id,
        (evidence_id,),
        key=f"assessment-{availability.value}",
    )
    protections_before = connection.execute(
        "SELECT COUNT(*) FROM recording_protections"
    ).fetchone()[0]
    set_source_availability(
        connection,
        recording_id=recording_id,
        availability=availability,
        reason_code="LIFECYCLE_TEST",
        authorized_by="operator",
        authorization_reference="assessment-lifecycle-test",
        operation_id=f"assessment-{availability.value}",
    )
    assert get_assessment(connection, assessment_id) is not None
    assert get_assessment_evidence(connection, assessment_id)[0].evidence_id == evidence_id
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM evidence WHERE evidence_id = ?", (evidence_id,)
        ).fetchone()[0]
        == 1
    )
    assert (
        connection.execute("SELECT COUNT(*) FROM recording_protections").fetchone()[0]
        == protections_before
        == 0
    )
    assert not {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    } & {"observations", "observation"}


def test_migration_from_review_foundation_backfills_zero_assessments(
    tmp_path: Path,
) -> None:
    old_migrations = tmp_path / "old-migrations"
    old_migrations.mkdir()
    for source in sorted(MIGRATIONS_DIRECTORY.glob("000[1-7]_*.sql")):
        shutil.copy2(source, old_migrations / source.name)
    database = tmp_path / "review-foundation.db"
    migrate(database, tmp_path / "backups", old_migrations)
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO stations (id, name, timezone, created_at) VALUES ('s', 'S', 'UTC', ?)",
            (NOW,),
        )
        audio = tmp_path / "legacy.wav"
        audio.write_bytes(b"audio")
        recording_id = insert_recording(
            connection,
            station_id="s",
            file_path=audio,
            recorded_at=NOW,
            duration_seconds=60,
            sample_rate=48000,
            channels=1,
            sample_format="S16_LE",
            file_size_bytes=5,
        )
        detection_id = insert_detection(
            connection, recording_id, "Turdus migratorius", "American Robin"
        )
        evidence_id = add_model_evidence(connection, detection_id, "pre-assessment")
        review_id = create_review(
            connection,
            detection_id=detection_id,
            decision=ReviewDecision.CONFIRM,
            reviewer_identity="reviewer",
            reviewer_role=ReviewerRole.USER,
            reviewed_at=NOW,
            reason_code="PREVIOUS_FOUNDATION",
            evidence=(ReviewEvidenceInput(evidence_id, ReviewEvidenceRole.PRIMARY),),
        )
        tables = ("detections", "evidence", "reviews", "review_evidence")
        before = {
            table: hashlib.sha256(
                json.dumps(
                    [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")],
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            for table in tables
        }
        connection.commit()

    applied = migrate(database, tmp_path / "backups")
    assert [item.version for item in applied] == [8, 9, 10, 11, 12]
    assert migrate(database, tmp_path / "backups") == []
    with sqlite3.connect(database) as connection:
        after = {
            table: hashlib.sha256(
                json.dumps(
                    [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")],
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            for table in tables
        }
        assert after == before
        assert connection.execute("SELECT COUNT(*) FROM assessments").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM assessment_evidence").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM reviews WHERE review_id = ?", (review_id,)
            ).fetchone()[0]
            == 1
        )
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
