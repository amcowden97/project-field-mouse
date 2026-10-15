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
    get_review,
    get_review_evidence,
    list_current_reviews,
    list_review_history,
)
from app.verification.reviews import ReviewInput, record_review


NOW = "2026-09-05T12:00:00+00:00"


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
    first_detection = _insert_detection(
        connection, recording_id, "Turdus migratorius", "American Robin"
    )
    second_detection = _insert_detection(
        connection, recording_id, "Cardinalis cardinalis", "Northern Cardinal"
    )
    connection.commit()
    return connection, audio, recording_id, first_detection, second_detection


def _insert_detection(
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


def add_evidence(
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


def add_review(
    connection: sqlite3.Connection,
    detection_id: int,
    evidence_id: int,
    *,
    decision: ReviewDecision = ReviewDecision.CONFIRM,
    reviewer: str = "reviewer-one",
    role: ReviewerRole = ReviewerRole.USER,
    supersedes: int | None = None,
    proposed_scientific_name: str | None = None,
    proposed_common_name: str | None = None,
) -> int:
    return create_review(
        connection,
        detection_id=detection_id,
        decision=decision,
        reviewer_identity=reviewer,
        reviewer_role=role,
        reviewed_at=NOW,
        reason_code="HUMAN_JUDGMENT",
        notes="Reviewed available scientific evidence.",
        evidence=(ReviewEvidenceInput(evidence_id, ReviewEvidenceRole.PRIMARY),),
        supersedes_review_id=supersedes,
        proposed_scientific_name=proposed_scientific_name,
        proposed_common_name=proposed_common_name,
    )


def test_valid_review_is_queryable_and_append_only(tmp_path: Path) -> None:
    connection, _, _, detection_id, _ = open_database(tmp_path)
    evidence_id = add_evidence(connection, detection_id, "valid-review")
    review_id = add_review(connection, detection_id, evidence_id)

    review = get_review(connection, review_id)
    assert review is not None
    assert review.decision == "CONFIRM"
    assert review.reviewer_identity == "reviewer-one"
    assert [item.evidence_id for item in get_review_evidence(connection, review_id)] == [
        evidence_id
    ]
    relationship_id = get_review_evidence(connection, review_id)[0].review_evidence_id
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(
            "UPDATE review_evidence SET relationship_role = 'CONTEXT' WHERE review_evidence_id = ?",
            (relationship_id,),
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(
            "DELETE FROM review_evidence WHERE review_evidence_id = ?",
            (relationship_id,),
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(
            "UPDATE reviews SET notes = 'rewritten' WHERE review_id = ?", (review_id,)
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute("DELETE FROM reviews WHERE review_id = ?", (review_id,))


@pytest.mark.parametrize("decision", ["ACCEPT", "PENDING_REVIEW", ""])
def test_invalid_decision_is_rejected(tmp_path: Path, decision: str) -> None:
    connection, _, _, detection_id, _ = open_database(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO reviews (
                review_identity, detection_id, decision, reviewer_identity,
                reviewer_role, reviewed_at, reason_code, created_at
            ) VALUES ('invalid-decision', ?, ?, 'user', 'USER', ?, 'TEST', ?)
            """,
            (detection_id, decision, NOW, NOW),
        )


def test_invalid_role_missing_detection_and_duplicate_identity_are_rejected(
    tmp_path: Path,
) -> None:
    connection, _, _, detection_id, _ = open_database(tmp_path)
    evidence_id = add_evidence(connection, detection_id, "identity-evidence")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO reviews (
                review_identity, detection_id, decision, reviewer_identity,
                reviewer_role, reviewed_at, reason_code, created_at
            ) VALUES ('invalid-role', ?, 'CONFIRM', 'user', 'ADMIN', ?, 'TEST', ?)
            """,
            (detection_id, NOW, NOW),
        )
    with pytest.raises(ScienceInvariantError, match="Unknown Detection"):
        create_review(
            connection,
            detection_id=999999,
            decision=ReviewDecision.CONFIRM,
            reviewer_identity="user",
            reviewer_role=ReviewerRole.USER,
            reviewed_at=NOW,
            reason_code="TEST",
            evidence=(ReviewEvidenceInput(evidence_id, ReviewEvidenceRole.PRIMARY),),
        )
    first = create_review(
        connection,
        detection_id=detection_id,
        decision=ReviewDecision.CONFIRM,
        reviewer_identity="user",
        reviewer_role=ReviewerRole.USER,
        reviewed_at=NOW,
        reason_code="TEST",
        evidence=(ReviewEvidenceInput(evidence_id, ReviewEvidenceRole.PRIMARY),),
        review_identity="stable-review",
    )
    assert first > 0
    with pytest.raises(ScienceInvariantError, match="UNIQUE"):
        create_review(
            connection,
            detection_id=detection_id,
            decision=ReviewDecision.REJECT,
            reviewer_identity="other-user",
            reviewer_role=ReviewerRole.USER,
            reviewed_at=NOW,
            reason_code="TEST",
            evidence=(ReviewEvidenceInput(evidence_id, ReviewEvidenceRole.PRIMARY),),
            review_identity="stable-review",
        )


def test_review_evidence_many_to_many_and_duplicate_rejection(tmp_path: Path) -> None:
    connection, _, _, detection_id, _ = open_database(tmp_path)
    first_evidence = add_evidence(connection, detection_id, "many-first")
    second_evidence = add_evidence(connection, detection_id, "many-second")
    first_review = create_review(
        connection,
        detection_id=detection_id,
        decision=ReviewDecision.CONFIRM,
        reviewer_identity="user-one",
        reviewer_role=ReviewerRole.USER,
        reviewed_at=NOW,
        reason_code="TEST",
        evidence=(
            ReviewEvidenceInput(first_evidence, ReviewEvidenceRole.PRIMARY),
            ReviewEvidenceInput(second_evidence, ReviewEvidenceRole.SUPPORTING),
        ),
    )
    second_review = add_review(
        connection,
        detection_id,
        first_evidence,
        decision=ReviewDecision.UNSURE,
        reviewer="user-two",
    )
    assert len(get_review_evidence(connection, first_review)) == 2
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM review_evidence WHERE evidence_id = ?", (first_evidence,)
        ).fetchone()[0]
        == 2
    )
    assert second_review != first_review
    with pytest.raises(ScienceInvariantError, match="Duplicate"):
        create_review(
            connection,
            detection_id=detection_id,
            decision=ReviewDecision.CONFIRM,
            reviewer_identity="user-three",
            reviewer_role=ReviewerRole.USER,
            reviewed_at=NOW,
            reason_code="TEST",
            evidence=(
                ReviewEvidenceInput(first_evidence, ReviewEvidenceRole.PRIMARY),
                ReviewEvidenceInput(first_evidence, ReviewEvidenceRole.CONTEXT),
            ),
        )


def test_incompatible_evidence_and_missing_new_review_evidence_are_rejected(
    tmp_path: Path,
) -> None:
    connection, _, _, first_detection, second_detection = open_database(tmp_path)
    incompatible = add_evidence(connection, second_detection, "incompatible")
    with pytest.raises(ScienceInvariantError, match="reviewed Detection"):
        add_review(connection, first_detection, incompatible)
    for role in (ReviewerRole.USER, ReviewerRole.EXPERT):
        with pytest.raises(ScienceInvariantError, match="require Evidence"):
            create_review(
                connection,
                detection_id=first_detection,
                decision=ReviewDecision.CONFIRM,
                reviewer_identity="reviewer",
                reviewer_role=role,
                reviewed_at=NOW,
                reason_code="TEST",
            )


def test_legacy_import_without_evidence_requires_legacy_provenance(tmp_path: Path) -> None:
    connection, _, _, detection_id, _ = open_database(tmp_path)
    legacy_id = record_review(
        connection,
        ReviewInput(detection_id, "verified", "legacy-reviewer"),
    )
    review_id = create_review(
        connection,
        detection_id=detection_id,
        decision=ReviewDecision.CONFIRM,
        reviewer_identity="legacy-reviewer",
        reviewer_role=ReviewerRole.LEGACY_IMPORT,
        reviewed_at=NOW,
        reason_code="RC1_1_VERIFIED",
        legacy_detection_review_id=legacy_id,
    )
    assert get_review_evidence(connection, review_id) == []
    with pytest.raises(ScienceInvariantError, match="legacy provenance"):
        create_review(
            connection,
            detection_id=detection_id,
            decision=ReviewDecision.CONFIRM,
            reviewer_identity="legacy-reviewer",
            reviewer_role=ReviewerRole.LEGACY_IMPORT,
            reviewed_at=NOW,
            reason_code="RC1_1_VERIFIED",
        )


@pytest.mark.parametrize(
    "decision",
    [ReviewDecision.CONFIRM, ReviewDecision.REJECT, ReviewDecision.UNSURE],
)
def test_initial_review_decisions(tmp_path: Path, decision: ReviewDecision) -> None:
    connection, _, _, detection_id, _ = open_database(tmp_path)
    evidence_id = add_evidence(connection, detection_id, f"decision-{decision.value}")
    review_id = add_review(connection, detection_id, evidence_id, decision=decision)
    assert get_review(connection, review_id).decision == decision.value  # type: ignore[union-attr]


def test_taxon_correction_preserves_historical_detection(tmp_path: Path) -> None:
    connection, _, _, detection_id, _ = open_database(tmp_path)
    evidence_id = add_evidence(connection, detection_id, "taxon-correction")
    before = tuple(
        connection.execute(
            """
            SELECT detector, scientific_name, common_name, confidence,
                   start_time, end_time, created_at
            FROM detections WHERE id = ?
            """,
            (detection_id,),
        ).fetchone()
    )
    review_id = add_review(
        connection,
        detection_id,
        evidence_id,
        decision=ReviewDecision.CORRECT_TAXON,
        proposed_scientific_name="Ixoreus naevius",
        proposed_common_name="Varied Thrush",
    )
    review = get_review(connection, review_id)
    assert review is not None
    assert review.proposed_scientific_name == "Ixoreus naevius"
    after = tuple(
        connection.execute(
            """
            SELECT detector, scientific_name, common_name, confidence,
                   start_time, end_time, created_at
            FROM detections WHERE id = ?
            """,
            (detection_id,),
        ).fetchone()
    )
    assert after == before
    with pytest.raises(ScienceInvariantError, match="proposed taxon"):
        add_review(
            connection,
            detection_id,
            evidence_id,
            decision=ReviewDecision.CORRECT_TAXON,
        )


def test_conflicting_reviews_coexist_without_implicit_supersession(tmp_path: Path) -> None:
    connection, _, _, detection_id, _ = open_database(tmp_path)
    evidence_id = add_evidence(connection, detection_id, "conflict")
    confirm = add_review(connection, detection_id, evidence_id)
    reject = add_review(
        connection,
        detection_id,
        evidence_id,
        decision=ReviewDecision.REJECT,
        reviewer="reviewer-two",
    )
    assert [review.review_id for review in list_review_history(connection, detection_id)] == [
        confirm,
        reject,
    ]
    assert {review.review_id for review in list_current_reviews(connection, detection_id)} == {
        confirm,
        reject,
    }


def test_supersession_is_explicit_same_detection_and_history_preserving(
    tmp_path: Path,
) -> None:
    connection, _, _, detection_id, other_detection = open_database(tmp_path)
    evidence_id = add_evidence(connection, detection_id, "supersession")
    original = add_review(connection, detection_id, evidence_id)
    replacement = add_review(
        connection,
        detection_id,
        evidence_id,
        decision=ReviewDecision.UNSURE,
        reviewer="reviewer-one",
        supersedes=original,
    )
    assert len(list_review_history(connection, detection_id)) == 2
    assert [item.review_id for item in list_current_reviews(connection, detection_id)] == [
        replacement
    ]
    other_evidence = add_evidence(connection, other_detection, "other-supersession")
    with pytest.raises(ScienceInvariantError, match="within one Detection"):
        add_review(
            connection,
            other_detection,
            other_evidence,
            supersedes=original,
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO reviews (
                review_id, review_identity, detection_id, decision,
                reviewer_identity, reviewer_role, reviewed_at, reason_code,
                supersedes_review_id, created_at
            ) VALUES (999, 'self-review', ?, 'CONFIRM', 'reviewer', 'USER',
                      ?, 'TEST', 999, ?)
            """,
            (detection_id, NOW, NOW),
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(
            "UPDATE reviews SET supersedes_review_id = ? WHERE review_id = ?",
            (replacement, original),
        )


def test_review_provenance_survives_source_lifecycle_change(tmp_path: Path) -> None:
    connection, _, recording_id, detection_id, _ = open_database(tmp_path)
    evidence_id = add_evidence(
        connection, detection_id, "source-lifecycle", recording_id=recording_id
    )
    review_id = add_review(connection, detection_id, evidence_id)
    set_source_availability(
        connection,
        recording_id=recording_id,
        availability=SourceAvailability.INTENTIONALLY_EXPIRED,
        reason_code="AUTHORIZED_RETENTION",
        authorized_by="operator",
        authorization_reference="retention-run-1",
        operation_id="review-source-expiration",
    )
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM detections WHERE id = ?", (detection_id,)
        ).fetchone()[0]
        == 1
    )
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM evidence WHERE evidence_id = ?", (evidence_id,)
        ).fetchone()[0]
        == 1
    )
    assert get_review(connection, review_id) is not None
    assert get_review_evidence(connection, review_id)[0].evidence_id == evidence_id


def test_legacy_backfill_is_conservative_idempotent_and_non_destructive(
    tmp_path: Path,
) -> None:
    old_migrations = tmp_path / "old-migrations"
    old_migrations.mkdir()
    for source in sorted(MIGRATIONS_DIRECTORY.glob("000[1-6]_*.sql")):
        shutil.copy2(source, old_migrations / source.name)
    database = tmp_path / "legacy.db"
    migrate(database, tmp_path / "backups", old_migrations)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO stations (id, name, timezone, created_at) VALUES ('s', 'S', 'UTC', ?)",
            (NOW,),
        )
        connection.execute(
            """
            INSERT INTO recordings (
                id, station_id, file_path, recorded_at, duration_seconds,
                sample_rate, channels, sample_format, file_size_bytes,
                processing_status, created_at
            ) VALUES (1, 's', ?, ?, 60, 48000, 1, 'S16_LE', 5, 'processed', ?)
            """,
            (str(tmp_path / "missing.wav"), NOW, NOW),
        )
        detection_id = _insert_detection(connection, 1, "Turdus migratorius", "American Robin")
        legacy_rows = (
            ("verified", None, None, 0.95),
            ("rejected", None, None, 0.05),
            ("corrected_species", "Ixoreus naevius", "Varied Thrush", 0.99),
            ("ignored", None, None, None),
            ("pending_review", None, None, None),
            ("corrected_species", None, None, 0.80),
        )
        for state, scientific_name, common_name, confidence_after in legacy_rows:
            connection.execute(
                """
                INSERT INTO detection_reviews (
                    detection_id, review_state, reviewed_at, reviewer,
                    original_scientific_name, original_common_name,
                    corrected_scientific_name, corrected_common_name, notes,
                    confidence_before, confidence_after, created_at
                ) VALUES (?, ?, ?, 'legacy-user', 'Turdus migratorius',
                          'American Robin', ?, ?, 'legacy note', 0.91, ?, ?)
                """,
                (
                    detection_id,
                    state,
                    NOW,
                    scientific_name,
                    common_name,
                    confidence_after,
                    NOW,
                ),
            )
        before = connection.execute("SELECT * FROM detection_reviews ORDER BY id").fetchall()
        connection.commit()

    applied = migrate(database, tmp_path / "backups")
    assert [item.version for item in applied] == [7, 8, 9, 10, 11]
    assert migrate(database, tmp_path / "backups") == []
    with sqlite3.connect(database) as connection:
        after = connection.execute("SELECT * FROM detection_reviews ORDER BY id").fetchall()
        assert after == before
        assert connection.execute(
            "SELECT decision, COUNT(*) FROM reviews GROUP BY decision ORDER BY decision"
        ).fetchall() == [
            ("CONFIRM", 1),
            ("CORRECT_TAXON", 1),
            ("REJECT", 1),
        ]
        assert connection.execute("SELECT COUNT(*) FROM review_evidence").fetchone()[0] == 0
        report = connection.execute(
            """
            SELECT total_legacy_reviews, migrated_count,
                   skipped_non_conclusive_count, ambiguous_count, invalid_count
            FROM review_schema_migration_runs
            """
        ).fetchone()
        assert report == (6, 3, 2, 0, 1)
        assert connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 3
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM detection_reviews WHERE id = 1")
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        review_columns = {row[1] for row in connection.execute("PRAGMA table_info(reviews)")}
        assert "confidence_after" not in review_columns


def test_legacy_adapter_can_create_explicit_canonical_provenance(tmp_path: Path) -> None:
    connection, _, _, detection_id, _ = open_database(tmp_path)
    evidence_id = add_evidence(connection, detection_id, "compatibility-adapter")
    legacy_id = record_review(
        connection,
        ReviewInput(
            detection_id,
            "verified",
            "operator",
            evidence_ids=(evidence_id,),
            reviewer_role="USER",
            reason_code="OPERATOR_CONFIRMATION",
        ),
    )
    canonical = connection.execute(
        "SELECT review_id, reviewer_role FROM reviews WHERE legacy_detection_review_id = ?",
        (legacy_id,),
    ).fetchone()
    assert canonical is not None
    assert canonical["reviewer_role"] == "USER"
    assert (
        get_review_evidence(connection, int(canonical["review_id"]))[0].evidence_id == evidence_id
    )
    assert connection.execute("SELECT COUNT(*) FROM detection_reviews").fetchone()[0] == 1
