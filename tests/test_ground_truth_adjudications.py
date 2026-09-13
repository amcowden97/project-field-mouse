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
from app.science.adjudications import (
    GroundTruthAdjudicationEligibilityReason,
    GroundTruthAdjudicationEvidenceInput,
    GroundTruthAdjudicationEvidenceRole,
    GroundTruthAdjudicationResult,
    GroundTruthAdjudicatorRole,
    create_ground_truth_adjudication,
    evaluate_ground_truth_adjudication_eligibility,
    get_ground_truth_adjudication,
    get_ground_truth_adjudication_evidence,
    list_current_ground_truth_adjudications,
    list_ground_truth_adjudication_history,
)
from app.science.assessments import AssessmentResult, create_assessment
from app.science.evidence import (
    EvidenceFamily,
    EvidenceSourceInput,
    EvidenceStance,
    SourceRole,
    append_evidence,
)
from app.science.ground_truth import (
    create_ground_truth_dataset,
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


NOW = "2026-09-12T18:00:00+00:00"


def add_detection(
    connection: sqlite3.Connection,
    recording_id: int,
    *,
    common_name: str = "American Robin",
    scientific_name: str = "Turdus migratorius",
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO detections (
            recording_id, detector, common_name, scientific_name,
            confidence, start_time, end_time, created_at
        ) VALUES (?, 'birdnet', ?, ?, 0.99, 1.0, 4.0, ?)
        """,
        (recording_id, common_name, scientific_name, NOW),
    )
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def add_model_evidence(
    connection: sqlite3.Connection,
    detection_id: int,
    recording_id: int,
    key: str,
) -> int:
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
        confidence_value=0.99,
        confidence_semantics="BirdNET classifier score",
        reason_code="MODEL_OUTPUT",
        reasoning="BirdNET emitted this bounded event claim.",
        observed_at=NOW,
        idempotency_key=key,
        claimed_scientific_name="Turdus migratorius",
        claimed_common_name="American Robin",
        sources=(EvidenceSourceInput(recording_id, SourceRole.PRIMARY, 1.0, 4.0),),
    )


def add_human_evidence(
    connection: sqlite3.Connection,
    detection_id: int,
    recording_ids: tuple[int, ...],
    key: str,
    *,
    family: str = "HUMAN",
    with_sources: bool = True,
) -> int:
    evidence_type = "EXPERT_CONFIRMATION" if family == "EXPERT" else "HUMAN_CONFIRMATION"
    cursor = connection.execute(
        """
        INSERT INTO evidence (
            evidence_identity, detection_id, family, evidence_type, stance,
            claimed_scientific_name, claimed_common_name, source_type,
            source_id, source_version, reason_code, reasoning, metadata_json,
            reviewer_id, reviewer_role, observed_at, created_at, idempotency_key
        ) VALUES (?, ?, ?, ?, 'SUPPORTS', 'Turdus migratorius',
                  'American Robin', 'HUMAN_REVIEW', ?, '1',
                  'CANONICAL_HUMAN_CONTRIBUTION',
                  'A scientific reviewer evaluated the bounded event.', '{}',
                  ?, ?, ?, ?, ?)
        """,
        (
            f"human-evidence:{key}",
            detection_id,
            family,
            evidence_type,
            f"reviewer:{key}",
            f"reviewer:{key}",
            family,
            NOW,
            NOW,
            key,
        ),
    )
    assert cursor.lastrowid is not None
    evidence_id = int(cursor.lastrowid)
    if with_sources:
        for recording_id in recording_ids:
            connection.execute(
                """
                INSERT INTO evidence_sources (
                    evidence_id, recording_id, source_role,
                    interval_start_seconds, interval_end_seconds, created_at
                ) VALUES (?, ?, 'PRIMARY', 1.0, 4.0, ?)
                """,
                (evidence_id, recording_id, NOW),
            )
    return evidence_id


def open_database(
    tmp_path: Path,
) -> tuple[sqlite3.Connection, int, int, int, int, int]:
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
    detection_id = add_detection(connection, recording_id)
    model_evidence_id = add_model_evidence(connection, detection_id, recording_id, "model-evidence")
    assessment_id = create_assessment(
        connection,
        detection_id=detection_id,
        result=AssessmentResult.SUPPORTED,
        evidence_ids=(model_evidence_id,),
        reason_code="EXPLICIT_ASSESSMENT",
        reasoning="Assessment retained for Ground Truth candidacy.",
        created_by="scientist",
        idempotency_key="assessment-one",
        created_at=NOW,
    )
    dataset_id = create_ground_truth_dataset(
        connection,
        dataset_identity="dataset:one",
        name="RC1.2 Candidate Events",
        purpose="Candidate events for explicit adjudication.",
        nomination_policy_version="candidate-v1",
        created_by="scientific-owner",
        created_at=NOW,
    )
    member_id = nominate_ground_truth_candidate(
        connection,
        dataset_id=dataset_id,
        assessment_id=assessment_id,
        nomination_reason_code="STRATIFIED_SAMPLE",
        nomination_reasoning="Selected as a bounded candidate event.",
        nominated_by="researcher-one",
        nomination_policy_version="candidate-v1",
        idempotency_key="candidate-one",
        created_at=NOW,
    )
    connection.commit()
    return (
        connection,
        recording_id,
        detection_id,
        model_evidence_id,
        assessment_id,
        member_id,
    )


def evidence_input(
    evidence_id: int,
    role: GroundTruthAdjudicationEvidenceRole = (GroundTruthAdjudicationEvidenceRole.PRIMARY),
) -> GroundTruthAdjudicationEvidenceInput:
    return GroundTruthAdjudicationEvidenceInput(evidence_id, role)


def adjudicate(
    connection: sqlite3.Connection,
    member_id: int,
    evidence_id: int,
    *,
    result: GroundTruthAdjudicationResult = (GroundTruthAdjudicationResult.CONFIRMED_TAXON),
    role: GroundTruthAdjudicatorRole = GroundTruthAdjudicatorRole.SCIENTIFIC_OWNER,
    key: str = "adjudication-one",
    supersedes: int | None = None,
) -> int:
    positive = result in {
        GroundTruthAdjudicationResult.CONFIRMED_TAXON,
        GroundTruthAdjudicationResult.ALTERNATE_TAXON,
    }
    return create_ground_truth_adjudication(
        connection,
        ground_truth_member_id=member_id,
        result=result,
        evidence=(evidence_input(evidence_id),),
        adjudicated_scientific_name=(
            "Ixoreus naevius"
            if result is GroundTruthAdjudicationResult.ALTERNATE_TAXON
            else "Turdus migratorius"
            if positive
            else None
        ),
        adjudicated_common_name=(
            "Varied Thrush"
            if result is GroundTruthAdjudicationResult.ALTERNATE_TAXON
            else "American Robin"
            if positive
            else None
        ),
        reason_code="EXPLICIT_ADJUDICATION",
        reasoning="The adjudicator explicitly evaluated the cited Evidence.",
        adjudicated_by="scientific-owner",
        adjudicator_role=role,
        policy_version="ground-truth-v1",
        idempotency_key=key,
        supersedes_adjudication_id=supersedes,
        created_at=NOW,
    )


def snapshot(connection: sqlite3.Connection, table: str) -> list[tuple]:
    return [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")]


def test_schema_is_append_only_controlled_and_candidate_stage_is_unchanged(
    tmp_path: Path,
) -> None:
    connection, recording_id, detection_id, _, _, member_id = open_database(tmp_path)
    human = add_human_evidence(connection, detection_id, (recording_id,), "schema-human")
    adjudication_id = adjudicate(connection, member_id, human)
    relationship = get_ground_truth_adjudication_evidence(connection, adjudication_id)[0]
    assert relationship.evidence_id == human
    assert relationship.relationship_role == "PRIMARY"
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(ground_truth_adjudications)")
    }
    indexes = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
    }
    assert not {"current", "active", "confidence", "observation_id"} & columns
    assert {
        "idx_ground_truth_adjudications_member_history",
        "idx_ground_truth_adjudications_result_history",
        "idx_ground_truth_adjudications_taxon",
        "idx_ground_truth_adjudications_supersedes",
        "idx_ground_truth_adjudication_evidence_adjudication",
        "idx_ground_truth_adjudication_evidence_evidence",
    } <= indexes
    assert (
        connection.execute(
            "SELECT stage FROM ground_truth_members WHERE ground_truth_member_id = ?",
            (member_id,),
        ).fetchone()[0]
        == "CANDIDATE_POOL"
    )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(
            "UPDATE ground_truth_adjudications SET result = 'UNRESOLVED' "
            "WHERE ground_truth_adjudication_id = ?",
            (adjudication_id,),
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(
            "DELETE FROM ground_truth_adjudication_evidence WHERE ground_truth_adjudication_id = ?",
            (adjudication_id,),
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(
            "DELETE FROM ground_truth_adjudications WHERE ground_truth_adjudication_id = ?",
            (adjudication_id,),
        )
    with pytest.raises(ScienceInvariantError, match="Unknown Ground Truth"):
        create_ground_truth_adjudication(
            connection,
            ground_truth_member_id=member_id,
            result="EXCLUDED",
            evidence=(evidence_input(human),),
            reason_code="TEST",
            reasoning="Dataset policy is not a scientific result.",
            adjudicated_by="owner",
            adjudicator_role=GroundTruthAdjudicatorRole.SCIENTIFIC_OWNER,
            policy_version="ground-truth-v1",
            idempotency_key="excluded-result",
        )


@pytest.mark.parametrize("result", list(GroundTruthAdjudicationResult))
def test_all_adjudication_results_are_explicit_and_valid(
    tmp_path: Path,
    result: GroundTruthAdjudicationResult,
) -> None:
    connection, recording_id, detection_id, _, _, member_id = open_database(tmp_path)
    human = add_human_evidence(connection, detection_id, (recording_id,), f"result-{result.value}")
    adjudication_id = adjudicate(
        connection,
        member_id,
        human,
        result=result,
        key=f"adjudication-{result.value}",
    )
    assert get_ground_truth_adjudication(connection, adjudication_id).result == result.value
    assert connection.execute("SELECT COUNT(*) FROM recording_protections").fetchone()[0] == 1


@pytest.mark.parametrize(
    "result",
    (
        GroundTruthAdjudicationResult.CONFIRMED_TAXON,
        GroundTruthAdjudicationResult.ALTERNATE_TAXON,
    ),
)
def test_positive_results_require_taxon(
    tmp_path: Path,
    result: GroundTruthAdjudicationResult,
) -> None:
    connection, recording_id, detection_id, _, _, member_id = open_database(tmp_path)
    human = add_human_evidence(connection, detection_id, (recording_id,), "taxon")
    with pytest.raises(ScienceInvariantError, match="requires an adjudicated taxon"):
        create_ground_truth_adjudication(
            connection,
            ground_truth_member_id=member_id,
            result=result,
            evidence=(evidence_input(human),),
            reason_code="TEST",
            reasoning="Missing required taxon.",
            adjudicated_by="owner",
            adjudicator_role=GroundTruthAdjudicatorRole.SCIENTIFIC_OWNER,
            policy_version="ground-truth-v1",
            idempotency_key=f"missing-taxon-{result.value}",
        )


@pytest.mark.parametrize(
    "result",
    (
        GroundTruthAdjudicationResult.DETECTOR_CLAIM_NOT_SUPPORTED,
        GroundTruthAdjudicationResult.UNRESOLVED,
    ),
)
def test_non_positive_results_forbid_taxon(
    tmp_path: Path,
    result: GroundTruthAdjudicationResult,
) -> None:
    connection, recording_id, detection_id, _, _, member_id = open_database(tmp_path)
    human = add_human_evidence(connection, detection_id, (recording_id,), "no-taxon")
    with pytest.raises(ScienceInvariantError, match="requires a NULL"):
        create_ground_truth_adjudication(
            connection,
            ground_truth_member_id=member_id,
            result=result,
            evidence=(evidence_input(human),),
            adjudicated_scientific_name="Turdus migratorius",
            reason_code="TEST",
            reasoning="Forbidden positive claim.",
            adjudicated_by="owner",
            adjudicator_role=GroundTruthAdjudicatorRole.SCIENTIFIC_OWNER,
            policy_version="ground-truth-v1",
            idempotency_key=f"forbidden-taxon-{result.value}",
        )


@pytest.mark.parametrize("role", list(GroundTruthAdjudicatorRole))
def test_authorized_adjudicator_roles(
    tmp_path: Path,
    role: GroundTruthAdjudicatorRole,
) -> None:
    connection, recording_id, detection_id, _, _, member_id = open_database(tmp_path)
    human = add_human_evidence(
        connection,
        detection_id,
        (recording_id,),
        role.value,
        family="EXPERT" if role is GroundTruthAdjudicatorRole.EXPERT else "HUMAN",
    )
    assert adjudicate(connection, member_id, human, role=role, key=role.value) > 0
    with pytest.raises(ScienceInvariantError, match="Unauthorized"):
        create_ground_truth_adjudication(
            connection,
            ground_truth_member_id=member_id,
            result=GroundTruthAdjudicationResult.UNRESOLVED,
            evidence=(evidence_input(human),),
            reason_code="TEST",
            reasoning="Unauthorized actor.",
            adjudicated_by="reviewer",
            adjudicator_role="USER",
            policy_version="ground-truth-v1",
            idempotency_key="unauthorized-role",
        )


def test_eligibility_helper_is_read_only_and_structured(tmp_path: Path) -> None:
    connection, recording_id, detection_id, _, _, member_id = open_database(tmp_path)
    human = add_human_evidence(connection, detection_id, (recording_id,), "eligibility")
    before = {
        table: snapshot(connection, table)
        for table in ("ground_truth_members", "recording_protections")
    }
    result = evaluate_ground_truth_adjudication_eligibility(
        connection,
        ground_truth_member_id=member_id,
        evidence=(evidence_input(human),),
        adjudicated_by="owner",
        adjudicator_role=GroundTruthAdjudicatorRole.SCIENTIFIC_OWNER,
        policy_version="ground-truth-v1",
        result=GroundTruthAdjudicationResult.CONFIRMED_TAXON,
    )
    assert result.eligible
    assert result.reasons == (GroundTruthAdjudicationEligibilityReason.ELIGIBLE.value,)
    assert result.required_recording_ids == (recording_id,)
    assert connection.execute("SELECT COUNT(*) FROM ground_truth_adjudications").fetchone()[0] == 0
    assert {table: snapshot(connection, table) for table in before} == before


def test_eligibility_reports_missing_actor_authority_and_policy(tmp_path: Path) -> None:
    connection, recording_id, detection_id, _, _, member_id = open_database(tmp_path)
    human = add_human_evidence(connection, detection_id, (recording_id,), "invalid-actor")
    result = evaluate_ground_truth_adjudication_eligibility(
        connection,
        ground_truth_member_id=member_id,
        evidence=(evidence_input(human),),
        adjudicated_by=" ",
        adjudicator_role="USER",
        policy_version=" ",
        result=GroundTruthAdjudicationResult.UNRESOLVED,
    )
    assert not result.eligible
    assert {
        GroundTruthAdjudicationEligibilityReason.ADJUDICATOR_IDENTITY_REQUIRED.value,
        GroundTruthAdjudicationEligibilityReason.ADJUDICATOR_AUTHORITY_REQUIRED.value,
        GroundTruthAdjudicationEligibilityReason.POLICY_VERSION_REQUIRED.value,
    } <= set(result.reasons)


def test_missing_canonical_human_evidence_and_legacy_only_review_fail(
    tmp_path: Path,
) -> None:
    connection, _, detection_id, model, _, member_id = open_database(tmp_path)
    legacy_cursor = connection.execute(
        """
        INSERT INTO detection_reviews (
            detection_id, review_state, reviewed_at, reviewer,
            original_scientific_name, original_common_name, notes,
            confidence_before, created_at
        ) VALUES (?, 'verified', ?, 'legacy-user', 'Turdus migratorius',
                  'American Robin', 'Legacy history.', 0.99, ?)
        """,
        (detection_id, NOW, NOW),
    )
    create_review(
        connection,
        detection_id=detection_id,
        decision=ReviewDecision.CONFIRM,
        reviewer_identity="legacy-user",
        reviewer_role=ReviewerRole.LEGACY_IMPORT,
        reviewed_at=NOW,
        reason_code="LEGACY_IMPORT",
        legacy_detection_review_id=int(legacy_cursor.lastrowid),
    )
    with pytest.raises(ScienceInvariantError, match="NO_CANONICAL_HUMAN_EVIDENCE"):
        adjudicate(connection, member_id, model)


@pytest.mark.parametrize(
    "availability",
    (SourceAvailability.INTENTIONALLY_EXPIRED, SourceAvailability.MISSING),
)
def test_unavailable_or_missing_required_source_is_rejected(
    tmp_path: Path,
    availability: SourceAvailability,
) -> None:
    connection, recording_id, detection_id, _, _, member_id = open_database(tmp_path)
    human = add_human_evidence(connection, detection_id, (recording_id,), availability.value)
    set_source_availability(
        connection,
        recording_id=recording_id,
        availability=availability,
        reason_code="SOURCE_CHANGE",
        authorized_by="auditor",
        authorization_reference="adjudication-source-test",
        operation_id=f"source-{availability.value}",
        occurred_at=NOW,
    )
    with pytest.raises(ScienceInvariantError, match="SOURCE_UNAVAILABLE"):
        adjudicate(connection, member_id, human)


def test_bounded_required_source_is_mandatory(tmp_path: Path) -> None:
    connection, _, detection_id, _, _, member_id = open_database(tmp_path)
    human = add_human_evidence(connection, detection_id, (), "unbounded-human", with_sources=False)
    with pytest.raises(ScienceInvariantError, match="INVALID_EVENT_PROVENANCE"):
        adjudicate(connection, member_id, human)


def test_all_evidence_must_target_candidate_detection(tmp_path: Path) -> None:
    connection, recording_id, _, _, _, member_id = open_database(tmp_path)
    other_detection = add_detection(
        connection,
        recording_id,
        common_name="Northern Cardinal",
        scientific_name="Cardinalis cardinalis",
    )
    unrelated = add_human_evidence(connection, other_detection, (recording_id,), "unrelated")
    with pytest.raises(ScienceInvariantError, match="INVALID_EVIDENCE_PROVENANCE"):
        adjudicate(connection, member_id, unrelated)


def test_duplicate_adjudication_evidence_is_rejected(tmp_path: Path) -> None:
    connection, recording_id, detection_id, _, _, member_id = open_database(tmp_path)
    human = add_human_evidence(connection, detection_id, (recording_id,), "duplicate")
    with pytest.raises(ScienceInvariantError, match="Duplicate"):
        create_ground_truth_adjudication(
            connection,
            ground_truth_member_id=member_id,
            result=GroundTruthAdjudicationResult.UNRESOLVED,
            evidence=(evidence_input(human), evidence_input(human)),
            reason_code="TEST",
            reasoning="Duplicate Evidence relationship.",
            adjudicated_by="owner",
            adjudicator_role=GroundTruthAdjudicatorRole.SCIENTIFIC_OWNER,
            policy_version="ground-truth-v1",
            idempotency_key="duplicate-evidence",
        )


@pytest.mark.parametrize("assessment_result", list(AssessmentResult))
def test_every_assessment_result_is_eligible_for_explicit_adjudication(
    tmp_path: Path,
    assessment_result: AssessmentResult,
) -> None:
    connection, recording_id, detection_id, _, _, _ = open_database(tmp_path)
    model = add_model_evidence(
        connection,
        detection_id,
        recording_id,
        f"assessment-input-{assessment_result.value}",
    )
    alternate = assessment_result is AssessmentResult.ALTERNATE_TAXON
    assessment_id = create_assessment(
        connection,
        detection_id=detection_id,
        result=assessment_result,
        evidence_ids=(model,),
        reason_code="ASSESSMENT_INPUT_TEST",
        reasoning="Any Assessment result may be adjudicated explicitly.",
        created_by="scientist",
        idempotency_key=f"assessment-input-{assessment_result.value}",
        alternate_scientific_name="Ixoreus naevius" if alternate else None,
        alternate_common_name="Varied Thrush" if alternate else None,
        created_at=NOW,
    )
    dataset_id = connection.execute("SELECT dataset_id FROM ground_truth_datasets").fetchone()[0]
    member_id = nominate_ground_truth_candidate(
        connection,
        dataset_id=dataset_id,
        assessment_id=assessment_id,
        nomination_reason_code="ASSESSMENT_INPUT_TEST",
        nomination_reasoning="Independent candidate for eligibility coverage.",
        nominated_by="scientist",
        nomination_policy_version="candidate-v1",
        idempotency_key=f"candidate-input-{assessment_result.value}",
        created_at=NOW,
    )
    human = add_human_evidence(
        connection,
        detection_id,
        (recording_id,),
        f"human-input-{assessment_result.value}",
    )
    assert (
        adjudicate(
            connection,
            member_id,
            human,
            result=GroundTruthAdjudicationResult.UNRESOLVED,
            key=f"adjudication-input-{assessment_result.value}",
        )
        > 0
    )


def test_adjudication_may_disagree_with_pinned_assessment(tmp_path: Path) -> None:
    connection, recording_id, detection_id, _, assessment_id, member_id = open_database(tmp_path)
    human = add_human_evidence(connection, detection_id, (recording_id,), "disagree")
    adjudication_id = adjudicate(
        connection,
        member_id,
        human,
        result=GroundTruthAdjudicationResult.DETECTOR_CLAIM_NOT_SUPPORTED,
    )
    assert get_ground_truth_adjudication(connection, adjudication_id).result == (
        GroundTruthAdjudicationResult.DETECTOR_CLAIM_NOT_SUPPORTED.value
    )
    assert (
        connection.execute(
            "SELECT result FROM assessments WHERE assessment_id = ?", (assessment_id,)
        ).fetchone()[0]
        == AssessmentResult.SUPPORTED.value
    )


def add_conflicting_reviews(
    connection: sqlite3.Connection,
    detection_id: int,
    recording_id: int,
) -> tuple[int, int]:
    confirming = add_human_evidence(connection, detection_id, (recording_id,), "confirming-review")
    rejecting = add_human_evidence(
        connection, detection_id, (recording_id,), "rejecting-review", family="EXPERT"
    )
    create_review(
        connection,
        detection_id=detection_id,
        decision=ReviewDecision.CONFIRM,
        reviewer_identity="reviewer-one",
        reviewer_role=ReviewerRole.USER,
        reviewed_at=NOW,
        reason_code="CONFIRM",
        evidence=(ReviewEvidenceInput(confirming, ReviewEvidenceRole.PRIMARY),),
    )
    create_review(
        connection,
        detection_id=detection_id,
        decision=ReviewDecision.REJECT,
        reviewer_identity="expert-one",
        reviewer_role=ReviewerRole.EXPERT,
        reviewed_at=NOW,
        reason_code="REJECT",
        evidence=(ReviewEvidenceInput(rejecting, ReviewEvidenceRole.PRIMARY),),
    )
    return confirming, rejecting


def test_non_expert_cannot_positively_resolve_material_review_conflict(
    tmp_path: Path,
) -> None:
    connection, recording_id, detection_id, _, _, member_id = open_database(tmp_path)
    confirming, _ = add_conflicting_reviews(connection, detection_id, recording_id)
    reviews_before = snapshot(connection, "reviews")
    with pytest.raises(ScienceInvariantError, match="ADJUDICATOR_AUTHORITY_REQUIRED"):
        adjudicate(connection, member_id, confirming)
    assert snapshot(connection, "reviews") == reviews_before
    assert connection.execute("SELECT COUNT(*) FROM ground_truth_adjudications").fetchone()[0] == 0


def test_expert_can_resolve_material_conflict_and_unresolved_remains_available(
    tmp_path: Path,
) -> None:
    connection, recording_id, detection_id, _, _, member_id = open_database(tmp_path)
    confirming, _ = add_conflicting_reviews(connection, detection_id, recording_id)
    expert_id = adjudicate(
        connection,
        member_id,
        confirming,
        role=GroundTruthAdjudicatorRole.EXPERT,
        key="expert-resolution",
    )
    assert expert_id > 0

    second_state = open_database(tmp_path / "unresolved")
    second, second_recording, second_detection, _, _, second_member = second_state
    human, _ = add_conflicting_reviews(second, second_detection, second_recording)
    unresolved_id = adjudicate(
        second,
        second_member,
        human,
        result=GroundTruthAdjudicationResult.UNRESOLVED,
        key="unresolved-conflict",
    )
    assert get_ground_truth_adjudication(second, unresolved_id).result == "UNRESOLVED"


def test_supersession_preserves_history_and_derives_heads(tmp_path: Path) -> None:
    connection, recording_id, detection_id, _, _, member_id = open_database(tmp_path)
    human = add_human_evidence(connection, detection_id, (recording_id,), "supersession")
    first = adjudicate(
        connection,
        member_id,
        human,
        result=GroundTruthAdjudicationResult.UNRESOLVED,
        key="first",
    )
    second = adjudicate(
        connection,
        member_id,
        human,
        result=GroundTruthAdjudicationResult.CONFIRMED_TAXON,
        key="second",
        supersedes=first,
    )
    assert [
        item.ground_truth_adjudication_id
        for item in list_ground_truth_adjudication_history(connection, member_id)
    ] == [first, second]
    assert [
        item.ground_truth_adjudication_id
        for item in list_current_ground_truth_adjudications(connection, member_id)
    ] == [second]
    assert get_ground_truth_adjudication(connection, first).result == "UNRESOLVED"


def test_multiple_current_heads_remain_visible(tmp_path: Path) -> None:
    connection, recording_id, detection_id, _, _, member_id = open_database(tmp_path)
    human = add_human_evidence(connection, detection_id, (recording_id,), "heads")
    first = adjudicate(
        connection,
        member_id,
        human,
        result=GroundTruthAdjudicationResult.UNRESOLVED,
        key="head-one",
    )
    second = adjudicate(
        connection,
        member_id,
        human,
        result=GroundTruthAdjudicationResult.DETECTOR_CLAIM_NOT_SUPPORTED,
        key="head-two",
    )
    assert {
        item.ground_truth_adjudication_id
        for item in list_current_ground_truth_adjudications(connection, member_id)
    } == {first, second}


def test_cross_member_and_self_supersession_are_rejected(tmp_path: Path) -> None:
    connection, recording_id, detection_id, model, assessment_id, member_id = open_database(
        tmp_path
    )
    human = add_human_evidence(connection, detection_id, (recording_id,), "cross-member")
    first = adjudicate(
        connection, member_id, human, result=GroundTruthAdjudicationResult.UNRESOLVED
    )
    dataset_id = connection.execute("SELECT dataset_id FROM ground_truth_datasets").fetchone()[0]
    second_assessment = create_assessment(
        connection,
        detection_id=detection_id,
        result=AssessmentResult.INCONCLUSIVE,
        evidence_ids=(model,),
        reason_code="SECOND_ASSESSMENT",
        reasoning="Independent candidate basis.",
        created_by="scientist",
        idempotency_key="assessment-two",
        created_at=NOW,
    )
    second_member = nominate_ground_truth_candidate(
        connection,
        dataset_id=dataset_id,
        assessment_id=second_assessment,
        nomination_reason_code="SECOND_CANDIDATE",
        nomination_reasoning="Independent candidate head.",
        nominated_by="scientist",
        nomination_policy_version="candidate-v1",
        idempotency_key="candidate-two",
        created_at=NOW,
    )
    with pytest.raises(ScienceInvariantError, match="within one member"):
        adjudicate(
            connection,
            second_member,
            human,
            result=GroundTruthAdjudicationResult.UNRESOLVED,
            key="cross-member-adjudication",
            supersedes=first,
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO ground_truth_adjudications (
                ground_truth_adjudication_id, adjudication_identity,
                ground_truth_member_id, result, reason_code, reasoning,
                adjudicated_by, adjudicator_role, policy_version,
                supersedes_adjudication_id, input_fingerprint,
                idempotency_key, created_at
            ) VALUES (999, 'self-adjudication', ?, 'UNRESOLVED', 'TEST',
                      'Self-reference.', 'expert', 'EXPERT', 'v1', 999, ?,
                      'self-adjudication', ?)
            """,
            (member_id, "f" * 64, NOW),
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(
            "UPDATE ground_truth_adjudications "
            "SET supersedes_adjudication_id = ? "
            "WHERE ground_truth_adjudication_id = ?",
            (first, first),
        )
    assert assessment_id > 0


def test_idempotent_retry_and_changed_input_rejection(tmp_path: Path) -> None:
    connection, recording_id, detection_id, _, _, member_id = open_database(tmp_path)
    human = add_human_evidence(connection, detection_id, (recording_id,), "retry")
    first = adjudicate(connection, member_id, human)
    assert adjudicate(connection, member_id, human) == first
    assert connection.execute("SELECT COUNT(*) FROM ground_truth_adjudications").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM recording_protections").fetchone()[0] == 1
    with pytest.raises(ScienceInvariantError, match="different inputs"):
        adjudicate(
            connection,
            member_id,
            human,
            result=GroundTruthAdjudicationResult.UNRESOLVED,
        )


def test_relationship_failure_rolls_back_complete_operation(tmp_path: Path) -> None:
    connection, recording_id, detection_id, _, _, member_id = open_database(tmp_path)
    human = add_human_evidence(connection, detection_id, (recording_id,), "link-failure")
    connection.execute(
        """
        CREATE TRIGGER force_adjudication_link_failure
        BEFORE INSERT ON ground_truth_adjudication_evidence
        BEGIN
            SELECT RAISE(ABORT, 'forced adjudication Evidence failure');
        END
        """
    )
    with pytest.raises(ScienceInvariantError, match="forced adjudication Evidence"):
        adjudicate(connection, member_id, human)
    assert connection.execute("SELECT COUNT(*) FROM ground_truth_adjudications").fetchone()[0] == 0
    assert (
        connection.execute("SELECT COUNT(*) FROM ground_truth_adjudication_evidence").fetchone()[0]
        == 0
    )
    assert connection.execute("SELECT COUNT(*) FROM recording_protections").fetchone()[0] == 0


def test_protection_failure_rolls_back_adjudication_and_relationships(
    tmp_path: Path,
) -> None:
    connection, recording_id, detection_id, _, _, member_id = open_database(tmp_path)
    human = add_human_evidence(connection, detection_id, (recording_id,), "protection-failure")
    connection.execute(
        """
        CREATE TRIGGER force_ground_truth_protection_failure
        BEFORE INSERT ON recording_protections
        BEGIN
            SELECT RAISE(ABORT, 'forced Ground Truth protection failure');
        END
        """
    )
    with pytest.raises(ScienceInvariantError, match="forced Ground Truth protection"):
        adjudicate(connection, member_id, human)
    assert connection.execute("SELECT COUNT(*) FROM ground_truth_adjudications").fetchone()[0] == 0
    assert (
        connection.execute("SELECT COUNT(*) FROM ground_truth_adjudication_evidence").fetchone()[0]
        == 0
    )
    assert connection.execute("SELECT COUNT(*) FROM recording_protections").fetchone()[0] == 0


def test_multiple_required_sources_receive_exact_ground_truth_protections(
    tmp_path: Path,
) -> None:
    connection, recording_id, detection_id, _, _, member_id = open_database(tmp_path)
    second_audio = tmp_path / "second.wav"
    second_audio.write_bytes(b"RIFF" + b"more-audio" * 100)
    second_recording = insert_recording(
        connection,
        station_id="station-one",
        file_path=second_audio,
        recorded_at=NOW,
        duration_seconds=60,
        sample_rate=48000,
        channels=1,
        sample_format="S16_LE",
        file_size_bytes=second_audio.stat().st_size,
    )
    human = add_human_evidence(
        connection,
        detection_id,
        (recording_id, second_recording),
        "multiple-sources",
    )
    adjudication_id = adjudicate(connection, member_id, human)
    identity = get_ground_truth_adjudication(connection, adjudication_id).adjudication_identity
    protections = connection.execute(
        """
        SELECT recording_id, protection_type, origin_type, origin_reference
        FROM recording_protections ORDER BY recording_id
        """
    ).fetchall()
    assert [tuple(row) for row in protections] == [
        (recording_id, "GROUND_TRUTH_EVIDENCE", "GROUND_TRUTH", identity),
        (second_recording, "GROUND_TRUTH_EVIDENCE", "GROUND_TRUTH", identity),
    ]


def test_unresolved_adjudication_protects_required_source(tmp_path: Path) -> None:
    connection, recording_id, detection_id, _, _, member_id = open_database(tmp_path)
    human = add_human_evidence(connection, detection_id, (recording_id,), "unresolved")
    adjudicate(
        connection,
        member_id,
        human,
        result=GroundTruthAdjudicationResult.UNRESOLVED,
    )
    assert (
        connection.execute(
            """
        SELECT protection_type FROM recording_protections
        WHERE recording_id = ? AND released_at IS NULL
        """,
            (recording_id,),
        ).fetchone()[0]
        == "GROUND_TRUTH_EVIDENCE"
    )
    with pytest.raises(ScienceInvariantError, match="protection blocks expiration"):
        set_source_availability(
            connection,
            recording_id=recording_id,
            availability=SourceAvailability.INTENTIONALLY_EXPIRED,
            reason_code="RETENTION_ATTEMPT",
            authorized_by="cleanup",
            authorization_reference="protected-ground-truth-source",
            operation_id="protected-expiry",
            occurred_at=NOW,
        )


def test_scientific_history_is_unchanged_and_no_future_state_is_created(
    tmp_path: Path,
) -> None:
    connection, recording_id, detection_id, _, _, member_id = open_database(tmp_path)
    human = add_human_evidence(connection, detection_id, (recording_id,), "snapshots")
    create_review(
        connection,
        detection_id=detection_id,
        decision=ReviewDecision.CONFIRM,
        reviewer_identity="reviewer",
        reviewer_role=ReviewerRole.USER,
        reviewed_at=NOW,
        reason_code="CONFIRM",
        evidence=(ReviewEvidenceInput(human, ReviewEvidenceRole.PRIMARY),),
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
    tables = (
        "recordings",
        "detections",
        "evidence",
        "reviews",
        "review_evidence",
        "assessments",
        "assessment_evidence",
        "verifications",
        "ground_truth_members",
    )
    before = {table: snapshot(connection, table) for table in tables}
    adjudicate(connection, member_id, human)
    assert {table: snapshot(connection, table) for table in tables} == before
    present = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert not {"observations", "observation", "species_trust"} & present


def test_candidate_stays_pinned_to_exact_superseded_assessment(tmp_path: Path) -> None:
    connection, recording_id, detection_id, model, assessment_id, member_id = open_database(
        tmp_path
    )
    human = add_human_evidence(connection, detection_id, (recording_id,), "pinned")
    replacement = create_assessment(
        connection,
        detection_id=detection_id,
        result=AssessmentResult.INCONCLUSIVE,
        evidence_ids=(model,),
        reason_code="RECONSIDERATION",
        reasoning="A later Assessment remains independent.",
        created_by="scientist",
        idempotency_key="replacement-assessment",
        supersedes_assessment_id=assessment_id,
        created_at=NOW,
    )
    adjudicate(connection, member_id, human)
    assert (
        connection.execute(
            "SELECT assessment_id FROM ground_truth_members WHERE ground_truth_member_id = ?",
            (member_id,),
        ).fetchone()[0]
        == assessment_id
    )
    assert replacement != assessment_id


def test_superseded_candidate_and_unknown_candidate_are_ineligible(
    tmp_path: Path,
) -> None:
    connection, recording_id, detection_id, _, assessment_id, member_id = open_database(tmp_path)
    human = add_human_evidence(connection, detection_id, (recording_id,), "candidate-head")
    dataset_id = connection.execute("SELECT dataset_id FROM ground_truth_datasets").fetchone()[0]
    nominate_ground_truth_candidate(
        connection,
        dataset_id=dataset_id,
        assessment_id=assessment_id,
        nomination_reason_code="RENOMINATION",
        nomination_reasoning="Explicit replacement candidate.",
        nominated_by="scientist",
        nomination_policy_version="candidate-v1",
        idempotency_key="replacement-candidate",
        supersedes_member_id=member_id,
        created_at=NOW,
    )
    with pytest.raises(ScienceInvariantError, match="NOT_CURRENT_CANDIDATE"):
        adjudicate(connection, member_id, human)
    result = evaluate_ground_truth_adjudication_eligibility(
        connection,
        ground_truth_member_id=999999,
        evidence=(evidence_input(human),),
        adjudicated_by="owner",
        adjudicator_role=GroundTruthAdjudicatorRole.SCIENTIFIC_OWNER,
        policy_version="ground-truth-v1",
        result=GroundTruthAdjudicationResult.UNRESOLVED,
    )
    assert not result.eligible
    assert GroundTruthAdjudicationEligibilityReason.CANDIDATE_NOT_FOUND.value in result.reasons


def test_migration_from_candidate_foundation_is_schema_only_and_idempotent(
    tmp_path: Path,
) -> None:
    old_migrations = tmp_path / "candidate-migrations"
    old_migrations.mkdir()
    for source in sorted(MIGRATIONS_DIRECTORY.glob("000[1-9]_*.sql")):
        shutil.copy2(source, old_migrations / source.name)
    database = tmp_path / "candidate.db"
    migrate(database, tmp_path / "backups-before", old_migrations)
    tables = (
        "recordings",
        "detections",
        "evidence",
        "reviews",
        "assessments",
        "ground_truth_datasets",
        "ground_truth_members",
        "recording_protections",
    )
    with sqlite3.connect(database) as connection:
        before = {
            table: hashlib.sha256(
                json.dumps(
                    [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")],
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            for table in tables
        }
    applied = migrate(database, tmp_path / "backups-after")
    assert [item.version for item in applied] == [10]
    assert migrate(database, tmp_path / "backups-after") == []
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
        assert (
            connection.execute("SELECT COUNT(*) FROM ground_truth_adjudications").fetchone()[0] == 0
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM ground_truth_adjudication_evidence"
            ).fetchone()[0]
            == 0
        )
        assert connection.execute("SELECT COUNT(*) FROM recording_protections").fetchone()[0] == 0
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
