PRAGMA foreign_keys = ON;

CREATE TABLE ground_truth_datasets (
    dataset_id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_identity TEXT NOT NULL UNIQUE
        CHECK (length(trim(dataset_identity)) BETWEEN 1 AND 200),
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 200),
    purpose TEXT NOT NULL CHECK (length(trim(purpose)) BETWEEN 1 AND 2000),
    nomination_policy_version TEXT NOT NULL
        CHECK (length(trim(nomination_policy_version)) BETWEEN 1 AND 200),
    created_by TEXT NOT NULL CHECK (length(trim(created_by)) BETWEEN 1 AND 200),
    created_at TEXT NOT NULL CHECK (length(trim(created_at)) > 0)
);

CREATE TRIGGER ground_truth_datasets_no_update
BEFORE UPDATE ON ground_truth_datasets
BEGIN
    SELECT RAISE(ABORT, 'ground truth datasets are append-only');
END;

CREATE TRIGGER ground_truth_datasets_no_delete
BEFORE DELETE ON ground_truth_datasets
BEGIN
    SELECT RAISE(ABORT, 'ground truth datasets are append-only');
END;

CREATE TABLE ground_truth_members (
    ground_truth_member_id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_identity TEXT NOT NULL UNIQUE
        CHECK (length(trim(member_identity)) BETWEEN 1 AND 200),
    dataset_id INTEGER NOT NULL,
    assessment_id INTEGER NOT NULL,
    stage TEXT NOT NULL DEFAULT 'CANDIDATE_POOL'
        CHECK (stage = 'CANDIDATE_POOL'),
    nomination_reason_code TEXT NOT NULL
        CHECK (length(trim(nomination_reason_code)) BETWEEN 1 AND 100),
    nomination_reasoning TEXT NOT NULL
        CHECK (length(trim(nomination_reasoning)) BETWEEN 1 AND 4000),
    nominated_by TEXT NOT NULL
        CHECK (length(trim(nominated_by)) BETWEEN 1 AND 200),
    nomination_policy_version TEXT NOT NULL
        CHECK (length(trim(nomination_policy_version)) BETWEEN 1 AND 200),
    supersedes_member_id INTEGER,
    input_fingerprint TEXT NOT NULL UNIQUE
        CHECK (length(input_fingerprint) = 64),
    idempotency_key TEXT NOT NULL UNIQUE
        CHECK (length(trim(idempotency_key)) BETWEEN 1 AND 200),
    created_at TEXT NOT NULL CHECK (length(trim(created_at)) > 0),
    FOREIGN KEY (dataset_id)
        REFERENCES ground_truth_datasets(dataset_id) ON DELETE RESTRICT,
    FOREIGN KEY (assessment_id)
        REFERENCES assessments(assessment_id) ON DELETE RESTRICT,
    FOREIGN KEY (supersedes_member_id)
        REFERENCES ground_truth_members(ground_truth_member_id) ON DELETE RESTRICT,
    CHECK (
        supersedes_member_id IS NULL
        OR supersedes_member_id != ground_truth_member_id
    )
);

CREATE INDEX idx_ground_truth_members_dataset_history
ON ground_truth_members(dataset_id, created_at, ground_truth_member_id);

CREATE INDEX idx_ground_truth_members_assessment
ON ground_truth_members(assessment_id, ground_truth_member_id);

CREATE INDEX idx_ground_truth_members_supersedes
ON ground_truth_members(supersedes_member_id, ground_truth_member_id)
WHERE supersedes_member_id IS NOT NULL;

CREATE TRIGGER ground_truth_members_supersession_same_dataset
BEFORE INSERT ON ground_truth_members
WHEN NEW.supersedes_member_id IS NOT NULL
 AND NOT EXISTS (
    SELECT 1 FROM ground_truth_members AS prior
    WHERE prior.ground_truth_member_id = NEW.supersedes_member_id
      AND prior.dataset_id = NEW.dataset_id
)
BEGIN
    SELECT RAISE(ABORT, 'superseded ground truth member must belong to the same dataset');
END;

CREATE TRIGGER ground_truth_members_supersession_no_cycle
BEFORE INSERT ON ground_truth_members
WHEN NEW.supersedes_member_id IS NOT NULL
 AND NEW.ground_truth_member_id IS NOT NULL
 AND EXISTS (
    WITH RECURSIVE ancestors(ground_truth_member_id) AS (
        SELECT NEW.supersedes_member_id
        UNION
        SELECT prior.supersedes_member_id
        FROM ground_truth_members AS prior
        JOIN ancestors
          ON prior.ground_truth_member_id = ancestors.ground_truth_member_id
        WHERE prior.supersedes_member_id IS NOT NULL
    )
    SELECT 1 FROM ancestors
    WHERE ground_truth_member_id = NEW.ground_truth_member_id
)
BEGIN
    SELECT RAISE(ABORT, 'ground truth membership supersession cycle');
END;

CREATE TRIGGER ground_truth_members_no_update
BEFORE UPDATE ON ground_truth_members
BEGIN
    SELECT RAISE(ABORT, 'ground truth members are append-only');
END;

CREATE TRIGGER ground_truth_members_no_delete
BEFORE DELETE ON ground_truth_members
BEGIN
    SELECT RAISE(ABORT, 'ground truth members are append-only');
END;
