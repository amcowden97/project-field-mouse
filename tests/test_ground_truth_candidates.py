from __future__ import annotations

import sqlite3
import shutil
from pathlib import Path

import pytest

from app.database.connection import insert_recording
from app.migrations import MIGRATIONS_DIRECTORY, migrate
from app.science import ScienceInvariantError
from app.science.assessments import AssessmentResult, create_assessment
from app.science.evidence import (
    EvidenceFamily,
    EvidenceSourceInput,
    EvidenceStance,
    SourceRole,
    append_evidence,
)
from app.science.ground_truth import (
    GroundTruthStage,
    create_ground_truth_dataset,
    get_ground_truth_dataset,
    get_ground_truth_member,
    list_current_ground_truth_members,
    list_ground_truth_member_history,
    nominate_ground_truth_candidate,
)
from app.science.recordings import SourceAvailability, set_source_availability
from app.science.reviews import (
    ReviewDecision,
    ReviewEvidenceInput,
    ReviewEvidenceRole,
    ReviewerRole,
    create_review,
)

NOW = "2026-09-05T18:00:00+00:00"


def open_database(
    tmp_path: Path,
    *,
    start_time: float | None = 1.0,
    end_time: float | None = 4.0,
    source_interval: tuple[float, float] | None = (1.0, 4.0),
) -> tuple[sqlite3.Connection, int, int, int]:
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
                      0.99, ?, ?, ?)
            """,
            (recording_id, start_time, end_time, NOW),
        ).lastrowid
    )
    sources = ()
    if source_interval is not None:
        sources = (
            EvidenceSourceInput(
                recording_id,
                SourceRole.PRIMARY,
                source_interval[0],
                source_interval[1],
            ),
        )
    evidence_id = append_evidence(
        connection,
        detection_id=detection_id,
        family=EvidenceFamily.MODEL,
        evidence_type="MODEL_PREDICTION",
        stance=EvidenceStance.SUPPORTS,
        source_type="DETECTOR",
        source_id="birdnet",
        source_version="0.2.16",
        algorithm_version="model-v1",
        confidence_value=0.99,
        confidence_semantics="BirdNET classifier score",
        reason_code="MODEL_OUTPUT",
        reasoning="BirdNET emitted this event claim.",
        observed_at=NOW,
        idempotency_key="evidence-one",
        claimed_scientific_name="Turdus migratorius",
        claimed_common_name="American Robin",
        sources=sources,
    )
    connection.commit()
    return connection, recording_id, detection_id, evidence_id


def add_assessment(
    connection: sqlite3.Connection,
    detection_id: int,
    evidence_id: int,
    *,
    result: AssessmentResult = AssessmentResult.SUPPORTED,
    key: str = "assessment-one",
    supersedes: int | None = None,
) -> int:
    alternate = result is AssessmentResult.ALTERNATE_TAXON
    return create_assessment(
        connection,
        detection_id=detection_id,
        result=result,
        evidence_ids=(evidence_id,),
        reason_code="EXPLICIT_ASSESSMENT",
        reasoning="Assessment retained for candidate research.",
        created_by="scientist",
        idempotency_key=key,
        alternate_scientific_name="Ixoreus naevius" if alternate else None,
        alternate_common_name="Varied Thrush" if alternate else None,
        supersedes_assessment_id=supersedes,
        created_at=NOW,
    )


def add_dataset(connection: sqlite3.Connection, identity: str = "dataset:one") -> int:
    return create_ground_truth_dataset(
        connection,
        dataset_identity=identity,
        name="RC1.2 Candidate Events",
        purpose="Candidate events for later Ground Truth adjudication.",
        nomination_policy_version="candidate-v1",
        created_by="scientific-owner",
        created_at=NOW,
    )


def nominate(
    connection: sqlite3.Connection,
    dataset_id: int,
    assessment_id: int,
    *,
    key: str = "nomination-one",
    reasoning: str = "Selected to represent a common high-confidence event.",
    supersedes: int | None = None,
) -> int:
    return nominate_ground_truth_candidate(
        connection,
        dataset_id=dataset_id,
        assessment_id=assessment_id,
        nomination_reason_code="STRATIFIED_SAMPLE",
        nomination_reasoning=reasoning,
        nominated_by="researcher-one",
        nomination_policy_version="candidate-v1",
        idempotency_key=key,
        supersedes_member_id=supersedes,
        created_at=NOW,
    )


def table_snapshot(connection: sqlite3.Connection, table: str) -> list[tuple]:
    return [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")]


def test_schema_is_candidate_only_and_identity_is_immutable(tmp_path: Path) -> None:
    connection, _, detection_id, evidence_id = open_database(tmp_path)
    dataset_id = add_dataset(connection)
    assessment_id = add_assessment(connection, detection_id, evidence_id)
    member_id = nominate(connection, dataset_id, assessment_id)

    assert get_ground_truth_dataset(connection, dataset_id).dataset_identity == "dataset:one"
    assert get_ground_truth_member(connection, member_id).stage == GroundTruthStage.CANDIDATE_POOL
    member_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(ground_truth_members)")
    }
    assert not {"current", "active", "calibration_eligible", "released_at"} & member_columns
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE ground_truth_datasets SET name = 'Changed' WHERE dataset_id = ?",
            (dataset_id,),
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE ground_truth_members SET stage = 'ADJUDICATED' "
            "WHERE ground_truth_member_id = ?",
            (member_id,),
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "DELETE FROM ground_truth_members WHERE ground_truth_member_id = ?",
            (member_id,),
        )
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint"):
        connection.execute(
            """
            INSERT INTO ground_truth_members (
                member_identity, dataset_id, assessment_id, stage,
                nomination_reason_code, nomination_reasoning, nominated_by,
                nomination_policy_version, input_fingerprint,
                idempotency_key, created_at
            ) VALUES ('invalid-stage', ?, ?, 'ADJUDICATED', 'TEST', 'Invalid',
                      'tester', 'candidate-v1', ?, 'invalid-stage', ?)
            """,
            (dataset_id, assessment_id, "f" * 64, NOW),
        )


def test_dataset_creation_is_idempotent_and_conflicts_fail(tmp_path: Path) -> None:
    connection, _, _, _ = open_database(tmp_path)
    first = add_dataset(connection)
    assert add_dataset(connection) == first
    with pytest.raises(ScienceInvariantError, match="different inputs"):
        create_ground_truth_dataset(
            connection,
            dataset_identity="dataset:one",
            name="Different",
            purpose="Candidate events for later Ground Truth adjudication.",
            nomination_policy_version="candidate-v1",
            created_by="scientific-owner",
        )
    assert connection.execute("SELECT COUNT(*) FROM ground_truth_datasets").fetchone()[0] == 1


@pytest.mark.parametrize("result", list(AssessmentResult))
def test_every_assessment_result_can_be_nominated(
    tmp_path: Path,
    result: AssessmentResult,
) -> None:
    connection, _, detection_id, evidence_id = open_database(tmp_path)
    dataset_id = add_dataset(connection)
    assessment_id = add_assessment(
        connection,
        detection_id,
        evidence_id,
        result=result,
        key=f"assessment-{result.value}",
    )
    member_id = nominate(
        connection,
        dataset_id,
        assessment_id,
        key=f"nomination-{result.value}",
    )
    assert get_ground_truth_member(connection, member_id).assessment_id == assessment_id


@pytest.mark.parametrize(
    ("start", "end"),
    (
        (None, 4.0),
        (1.0, None),
        (2.0, 2.0),
        (4.0, 1.0),
        (-1.0, 2.0),
        (1.0, float("inf")),
    ),
)
def test_unbounded_detection_cannot_be_nominated(
    tmp_path: Path,
    start: float | None,
    end: float | None,
) -> None:
    connection, _, detection_id, evidence_id = open_database(
        tmp_path,
        start_time=start,
        end_time=end,
        source_interval=None,
    )
    assessment_id = add_assessment(connection, detection_id, evidence_id)
    with pytest.raises(ScienceInvariantError, match="bounded Detection"):
        nominate(connection, add_dataset(connection), assessment_id)
    assert connection.execute("SELECT COUNT(*) FROM ground_truth_members").fetchone()[0] == 0


@pytest.mark.parametrize(
    "source_interval",
    (None, (0.0, 0.5), (4.5, 6.0), (0.0, 2.0), (3.0, 5.0)),
)
def test_assessment_requires_source_interval_covering_detection(
    tmp_path: Path,
    source_interval: tuple[float, float] | None,
) -> None:
    connection, _, detection_id, evidence_id = open_database(
        tmp_path,
        source_interval=source_interval,
    )
    assessment_id = add_assessment(connection, detection_id, evidence_id)
    with pytest.raises(ScienceInvariantError, match="bounded source provenance"):
        nominate(connection, add_dataset(connection), assessment_id)


def test_unknown_assessment_and_unavailable_source_fail(tmp_path: Path) -> None:
    connection, recording_id, _, _ = open_database(tmp_path)
    dataset_id = add_dataset(connection)
    with pytest.raises(ScienceInvariantError, match="Unknown Assessment"):
        nominate(connection, dataset_id, 999999)
    set_source_availability(
        connection,
        recording_id=recording_id,
        availability=SourceAvailability.MISSING,
        reason_code="SOURCE_NOT_FOUND",
        authorized_by="auditor",
        authorization_reference="audit-one",
        operation_id="missing-before-nomination",
        occurred_at=NOW,
    )
    detection_id = connection.execute("SELECT id FROM detections").fetchone()[0]
    evidence_id = connection.execute("SELECT evidence_id FROM evidence").fetchone()[0]
    assessment_id = add_assessment(connection, detection_id, evidence_id)
    with pytest.raises(ScienceInvariantError, match="AVAILABLE"):
        nominate(connection, dataset_id, assessment_id)


def test_nomination_requires_dataset_policy_and_provenance_fields(tmp_path: Path) -> None:
    connection, _, detection_id, evidence_id = open_database(tmp_path)
    assessment_id = add_assessment(connection, detection_id, evidence_id)
    with pytest.raises(ScienceInvariantError, match="Unknown Ground Truth dataset"):
        nominate(connection, 999999, assessment_id)
    dataset_id = add_dataset(connection)
    with pytest.raises(ScienceInvariantError, match="policy version"):
        nominate_ground_truth_candidate(
            connection,
            dataset_id=dataset_id,
            assessment_id=assessment_id,
            nomination_reason_code="STRATIFIED_SAMPLE",
            nomination_reasoning="Selected candidate.",
            nominated_by="researcher-one",
            nomination_policy_version="different-policy",
            idempotency_key="different-policy",
        )
    with pytest.raises(ScienceInvariantError, match="provenance"):
        nominate_ground_truth_candidate(
            connection,
            dataset_id=dataset_id,
            assessment_id=assessment_id,
            nomination_reason_code="",
            nomination_reasoning="Selected candidate.",
            nominated_by="researcher-one",
            nomination_policy_version="candidate-v1",
            idempotency_key="missing-reason-code",
        )
    assert connection.execute("SELECT COUNT(*) FROM ground_truth_members").fetchone()[0] == 0


def test_nomination_idempotency_and_atomic_failure(tmp_path: Path) -> None:
    connection, _, detection_id, evidence_id = open_database(tmp_path)
    dataset_id = add_dataset(connection)
    assessment_id = add_assessment(connection, detection_id, evidence_id)
    first = nominate(connection, dataset_id, assessment_id)
    assert nominate(connection, dataset_id, assessment_id) == first
    with pytest.raises(ScienceInvariantError, match="different inputs"):
        nominate(
            connection,
            dataset_id,
            assessment_id,
            reasoning="Materially changed nomination.",
        )
    assert connection.execute("SELECT COUNT(*) FROM ground_truth_members").fetchone()[0] == 1

    connection.execute("""
        CREATE TRIGGER force_ground_truth_failure
        BEFORE INSERT ON ground_truth_members
        BEGIN SELECT RAISE(ABORT, 'forced nomination failure'); END
        """)
    with pytest.raises(ScienceInvariantError, match="forced nomination failure"):
        nominate(connection, dataset_id, assessment_id, key="forced-failure")
    assert connection.execute("SELECT COUNT(*) FROM ground_truth_members").fetchone()[0] == 1


def test_caller_supplied_member_identity_is_part_of_idempotency(tmp_path: Path) -> None:
    connection, _, detection_id, evidence_id = open_database(tmp_path)
    dataset_id = add_dataset(connection)
    assessment_id = add_assessment(connection, detection_id, evidence_id)
    arguments = {
        "dataset_id": dataset_id,
        "assessment_id": assessment_id,
        "nomination_reason_code": "STRATIFIED_SAMPLE",
        "nomination_reasoning": "Selected candidate.",
        "nominated_by": "researcher-one",
        "nomination_policy_version": "candidate-v1",
        "idempotency_key": "identity-retry",
        "member_identity": "ground-truth-member:stable-one",
    }
    first = nominate_ground_truth_candidate(connection, **arguments)
    assert nominate_ground_truth_candidate(connection, **arguments) == first
    arguments["member_identity"] = "ground-truth-member:different"
    with pytest.raises(ScienceInvariantError, match="different inputs"):
        nominate_ground_truth_candidate(connection, **arguments)


def test_supersession_is_same_dataset_append_only_and_heads_are_derived(
    tmp_path: Path,
) -> None:
    connection, _, detection_id, evidence_id = open_database(tmp_path)
    first_dataset = add_dataset(connection)
    second_dataset = add_dataset(connection, "dataset:two")
    first_assessment = add_assessment(connection, detection_id, evidence_id)
    first_member = nominate(connection, first_dataset, first_assessment)
    second_assessment = add_assessment(
        connection,
        detection_id,
        evidence_id,
        result=AssessmentResult.INCONCLUSIVE,
        key="assessment-two",
        supersedes=first_assessment,
    )
    with pytest.raises(ScienceInvariantError, match="one dataset"):
        nominate(
            connection,
            second_dataset,
            second_assessment,
            key="cross-dataset",
            supersedes=first_member,
        )
    second_member = nominate(
        connection,
        first_dataset,
        second_assessment,
        key="nomination-two",
        supersedes=first_member,
    )
    assert [
        item.ground_truth_member_id
        for item in list_ground_truth_member_history(connection, first_dataset)
    ] == [first_member, second_member]
    assert [
        item.ground_truth_member_id
        for item in list_current_ground_truth_members(connection, first_dataset)
    ] == [second_member]
    assert get_ground_truth_member(connection, first_member).assessment_id == first_assessment


def test_multiple_unsuperseded_heads_do_not_invent_consensus(tmp_path: Path) -> None:
    connection, _, detection_id, evidence_id = open_database(tmp_path)
    dataset_id = add_dataset(connection)
    first = add_assessment(connection, detection_id, evidence_id)
    second = add_assessment(
        connection,
        detection_id,
        evidence_id,
        result=AssessmentResult.NOT_SUPPORTED,
        key="conflicting-assessment",
    )
    members = (
        nominate(connection, dataset_id, first, key="candidate-one"),
        nominate(connection, dataset_id, second, key="candidate-two"),
    )
    assert (
        tuple(
            item.ground_truth_member_id
            for item in list_current_ground_truth_members(connection, dataset_id)
        )
        == members
    )


def test_nomination_does_not_mutate_scientific_history_or_create_side_effects(
    tmp_path: Path,
) -> None:
    connection, _, detection_id, evidence_id = open_database(tmp_path)
    assessment_id = add_assessment(connection, detection_id, evidence_id)
    before = {
        table: table_snapshot(connection, table)
        for table in ("detections", "evidence", "reviews", "assessments")
    }
    nominate(connection, add_dataset(connection), assessment_id)
    after = {table: table_snapshot(connection, table) for table in before}
    assert after == before
    assert connection.execute("SELECT COUNT(*) FROM recording_protections").fetchone()[0] == 0
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert not {"observations", "observation", "species_trust"} & tables


def test_truth_looking_states_never_create_members_automatically(tmp_path: Path) -> None:
    connection, _, detection_id, evidence_id = open_database(tmp_path)
    add_dataset(connection)
    create_review(
        connection,
        detection_id=detection_id,
        decision=ReviewDecision.CONFIRM,
        reviewer_identity="reviewer-one",
        reviewer_role=ReviewerRole.USER,
        reviewed_at=NOW,
        reason_code="HUMAN_CONFIRMATION",
        evidence=(ReviewEvidenceInput(evidence_id, ReviewEvidenceRole.PRIMARY),),
    )
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
    add_assessment(connection, detection_id, evidence_id)
    assert connection.execute("SELECT COUNT(*) FROM ground_truth_members").fetchone()[0] == 0


@pytest.mark.parametrize(
    "availability",
    (SourceAvailability.INTENTIONALLY_EXPIRED, SourceAvailability.MISSING),
)
def test_source_lifecycle_preserves_candidate_history(
    tmp_path: Path,
    availability: SourceAvailability,
) -> None:
    connection, recording_id, detection_id, evidence_id = open_database(tmp_path)
    assessment_id = add_assessment(connection, detection_id, evidence_id)
    member_id = nominate(connection, add_dataset(connection), assessment_id)
    set_source_availability(
        connection,
        recording_id=recording_id,
        availability=availability,
        reason_code="POST_NOMINATION_SOURCE_CHANGE",
        authorized_by="operator",
        authorization_reference="source-lifecycle-test",
        operation_id=f"candidate-{availability.value}",
        occurred_at=NOW,
    )
    assert get_ground_truth_member(connection, member_id).assessment_id == assessment_id
    assert connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM assessments").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM recording_protections").fetchone()[0] == 0
    state = connection.execute(
        "SELECT source_availability FROM recordings WHERE id = ?", (recording_id,)
    ).fetchone()[0]
    assert state == availability.value
    assert nominate(connection, add_dataset(connection), assessment_id) == member_id


def test_foreign_keys_restrict_scientific_history_deletion(tmp_path: Path) -> None:
    connection, _, detection_id, evidence_id = open_database(tmp_path)
    dataset_id = add_dataset(connection)
    assessment_id = add_assessment(connection, detection_id, evidence_id)
    nominate(connection, dataset_id, assessment_id)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("DELETE FROM assessments WHERE assessment_id = ?", (assessment_id,))
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("DELETE FROM ground_truth_datasets WHERE dataset_id = ?", (dataset_id,))
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_migration_from_assessment_foundation_is_schema_only_and_idempotent(
    tmp_path: Path,
) -> None:
    old_migrations = tmp_path / "assessment-migrations"
    old_migrations.mkdir()
    for source in sorted(MIGRATIONS_DIRECTORY.glob("000[1-8]_*.sql")):
        shutil.copy2(source, old_migrations / source.name)
    database = tmp_path / "assessment-foundation.db"
    migrate(database, tmp_path / "backups", old_migrations)
    with sqlite3.connect(database) as connection:
        before = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "recordings",
                "detections",
                "evidence",
                "reviews",
                "assessments",
                "recording_protections",
            )
        }
    applied = migrate(database, tmp_path / "backups")
    assert [(item.version, item.name) for item in applied] == [
        (9, "ground_truth_candidate_membership"),
        (10, "ground_truth_adjudication_provenance"),
        (11, "station_sync_identity_outbox"),
    ]
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {"ground_truth_datasets", "ground_truth_members"} <= tables
        assert connection.execute("SELECT COUNT(*) FROM ground_truth_datasets").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM ground_truth_members").fetchone()[0] == 0
        after = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in before
        }
        assert after == before
        assert not {"observations", "observation", "species_trust"} & tables
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert migrate(database, tmp_path / "backups") == []
