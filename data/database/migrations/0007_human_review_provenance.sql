PRAGMA foreign_keys = ON;

CREATE TRIGGER detection_reviews_legacy_no_update
BEFORE UPDATE ON detection_reviews
BEGIN
    SELECT RAISE(ABORT, 'legacy detection reviews are append-only');
END;

CREATE TRIGGER detection_reviews_legacy_no_delete
BEFORE DELETE ON detection_reviews
BEGIN
    SELECT RAISE(ABORT, 'legacy detection reviews are append-only');
END;

CREATE TABLE reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_identity TEXT NOT NULL UNIQUE
        CHECK (length(trim(review_identity)) BETWEEN 1 AND 200),
    detection_id INTEGER NOT NULL,
    decision TEXT NOT NULL CHECK (
        decision IN ('CONFIRM', 'REJECT', 'UNSURE', 'CORRECT_TAXON')
    ),
    reviewer_identity TEXT NOT NULL
        CHECK (length(trim(reviewer_identity)) BETWEEN 1 AND 200),
    reviewer_role TEXT NOT NULL CHECK (
        reviewer_role IN ('USER', 'EXPERT', 'LEGACY_IMPORT')
    ),
    reviewed_at TEXT NOT NULL CHECK (length(trim(reviewed_at)) > 0),
    reason_code TEXT NOT NULL CHECK (length(trim(reason_code)) BETWEEN 1 AND 100),
    notes TEXT NOT NULL DEFAULT '' CHECK (length(notes) <= 4000),
    proposed_scientific_name TEXT,
    proposed_common_name TEXT,
    supersedes_review_id INTEGER,
    legacy_detection_review_id INTEGER UNIQUE,
    created_at TEXT NOT NULL CHECK (length(trim(created_at)) > 0),
    FOREIGN KEY (detection_id) REFERENCES detections(id) ON DELETE RESTRICT,
    FOREIGN KEY (supersedes_review_id) REFERENCES reviews(review_id) ON DELETE RESTRICT,
    FOREIGN KEY (legacy_detection_review_id)
        REFERENCES detection_reviews(id) ON DELETE RESTRICT,
    CHECK (supersedes_review_id IS NULL OR supersedes_review_id != review_id),
    CHECK (
        (decision = 'CORRECT_TAXON' AND (
            length(trim(coalesce(proposed_scientific_name, ''))) > 0
            OR length(trim(coalesce(proposed_common_name, ''))) > 0
        ))
        OR (decision != 'CORRECT_TAXON'
            AND proposed_scientific_name IS NULL
            AND proposed_common_name IS NULL)
    ),
    CHECK (
        reviewer_role != 'LEGACY_IMPORT'
        OR legacy_detection_review_id IS NOT NULL
    )
);

CREATE INDEX idx_reviews_detection_history
ON reviews(detection_id, reviewed_at, review_id);

CREATE INDEX idx_reviews_reviewer_history
ON reviews(reviewer_identity, reviewed_at, review_id);

CREATE INDEX idx_reviews_decision_history
ON reviews(decision, reviewed_at, review_id);

CREATE INDEX idx_reviews_supersedes
ON reviews(supersedes_review_id, review_id)
WHERE supersedes_review_id IS NOT NULL;

CREATE TRIGGER reviews_legacy_detection_compatible
BEFORE INSERT ON reviews
WHEN NEW.legacy_detection_review_id IS NOT NULL
 AND NOT EXISTS (
    SELECT 1 FROM detection_reviews AS legacy
    WHERE legacy.id = NEW.legacy_detection_review_id
      AND legacy.detection_id = NEW.detection_id
 )
BEGIN
    SELECT RAISE(ABORT, 'legacy review must evaluate the same detection');
END;

CREATE TRIGGER reviews_supersession_same_detection
BEFORE INSERT ON reviews
WHEN NEW.supersedes_review_id IS NOT NULL
 AND NOT EXISTS (
    SELECT 1 FROM reviews AS prior
    WHERE prior.review_id = NEW.supersedes_review_id
      AND prior.detection_id = NEW.detection_id
 )
BEGIN
    SELECT RAISE(ABORT, 'superseded review must evaluate the same detection');
END;

CREATE TRIGGER reviews_supersession_no_cycle
BEFORE INSERT ON reviews
WHEN NEW.supersedes_review_id IS NOT NULL
 AND NEW.review_id IS NOT NULL
 AND EXISTS (
    WITH RECURSIVE ancestors(review_id) AS (
        SELECT NEW.supersedes_review_id
        UNION
        SELECT prior.supersedes_review_id
        FROM reviews AS prior
        JOIN ancestors ON prior.review_id = ancestors.review_id
        WHERE prior.supersedes_review_id IS NOT NULL
    )
    SELECT 1 FROM ancestors WHERE review_id = NEW.review_id
 )
BEGIN
    SELECT RAISE(ABORT, 'review supersession cycle');
END;

CREATE TRIGGER reviews_no_update
BEFORE UPDATE ON reviews
BEGIN
    SELECT RAISE(ABORT, 'reviews are append-only');
END;

CREATE TRIGGER reviews_no_delete
BEFORE DELETE ON reviews
BEGIN
    SELECT RAISE(ABORT, 'reviews are append-only');
END;

CREATE TABLE review_evidence (
    review_evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id INTEGER NOT NULL,
    evidence_id INTEGER NOT NULL,
    relationship_role TEXT NOT NULL CHECK (
        relationship_role IN ('PRIMARY', 'SUPPORTING', 'CONTEXT')
    ),
    created_at TEXT NOT NULL,
    FOREIGN KEY (review_id) REFERENCES reviews(review_id) ON DELETE RESTRICT,
    FOREIGN KEY (evidence_id) REFERENCES evidence(evidence_id) ON DELETE RESTRICT,
    UNIQUE (review_id, evidence_id)
);

CREATE INDEX idx_review_evidence_review
ON review_evidence(review_id, review_evidence_id);

CREATE INDEX idx_review_evidence_evidence
ON review_evidence(evidence_id, review_id);

CREATE TRIGGER review_evidence_detection_compatible
BEFORE INSERT ON review_evidence
WHEN NOT EXISTS (
    SELECT 1
    FROM reviews AS review
    JOIN evidence AS item ON item.evidence_id = NEW.evidence_id
    WHERE review.review_id = NEW.review_id
      AND review.detection_id = item.detection_id
)
BEGIN
    SELECT RAISE(ABORT, 'review evidence must evaluate the same detection');
END;

CREATE TRIGGER review_evidence_no_update
BEFORE UPDATE ON review_evidence
BEGIN
    SELECT RAISE(ABORT, 'review evidence is append-only');
END;

CREATE TRIGGER review_evidence_no_delete
BEFORE DELETE ON review_evidence
BEGIN
    SELECT RAISE(ABORT, 'review evidence is append-only');
END;

CREATE TABLE review_schema_migration_runs (
    migration_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_version INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    total_legacy_reviews INTEGER NOT NULL,
    migrated_count INTEGER NOT NULL,
    skipped_non_conclusive_count INTEGER NOT NULL,
    ambiguous_count INTEGER NOT NULL,
    invalid_count INTEGER NOT NULL,
    backfill_ms REAL NOT NULL,
    warnings_json TEXT NOT NULL CHECK (json_valid(warnings_json))
);
