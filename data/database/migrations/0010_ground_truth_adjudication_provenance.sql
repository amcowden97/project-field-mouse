PRAGMA foreign_keys = ON;

CREATE TABLE ground_truth_adjudications (
    ground_truth_adjudication_id INTEGER PRIMARY KEY AUTOINCREMENT,
    adjudication_identity TEXT NOT NULL UNIQUE
        CHECK (length(trim(adjudication_identity)) BETWEEN 1 AND 200),
    ground_truth_member_id INTEGER NOT NULL,
    result TEXT NOT NULL CHECK (
        result IN (
            'CONFIRMED_TAXON', 'DETECTOR_CLAIM_NOT_SUPPORTED',
            'ALTERNATE_TAXON', 'UNRESOLVED'
        )
    ),
    adjudicated_scientific_name TEXT,
    adjudicated_common_name TEXT,
    reason_code TEXT NOT NULL
        CHECK (length(trim(reason_code)) BETWEEN 1 AND 100),
    reasoning TEXT NOT NULL CHECK (length(trim(reasoning)) BETWEEN 1 AND 4000),
    adjudicated_by TEXT NOT NULL
        CHECK (length(trim(adjudicated_by)) BETWEEN 1 AND 200),
    adjudicator_role TEXT NOT NULL CHECK (
        adjudicator_role IN ('SCIENTIFIC_OWNER', 'EXPERT')
    ),
    policy_version TEXT NOT NULL
        CHECK (length(trim(policy_version)) BETWEEN 1 AND 200),
    supersedes_adjudication_id INTEGER,
    input_fingerprint TEXT NOT NULL UNIQUE
        CHECK (length(input_fingerprint) = 64),
    idempotency_key TEXT NOT NULL UNIQUE
        CHECK (length(trim(idempotency_key)) BETWEEN 1 AND 200),
    created_at TEXT NOT NULL CHECK (length(trim(created_at)) > 0),
    FOREIGN KEY (ground_truth_member_id)
        REFERENCES ground_truth_members(ground_truth_member_id) ON DELETE RESTRICT,
    FOREIGN KEY (supersedes_adjudication_id)
        REFERENCES ground_truth_adjudications(ground_truth_adjudication_id)
        ON DELETE RESTRICT,
    CHECK (
        supersedes_adjudication_id IS NULL
        OR supersedes_adjudication_id != ground_truth_adjudication_id
    ),
    CHECK (
        (result IN ('CONFIRMED_TAXON', 'ALTERNATE_TAXON') AND (
            length(trim(coalesce(adjudicated_scientific_name, ''))) > 0
            OR length(trim(coalesce(adjudicated_common_name, ''))) > 0
        ))
        OR (result IN ('DETECTOR_CLAIM_NOT_SUPPORTED', 'UNRESOLVED')
            AND adjudicated_scientific_name IS NULL
            AND adjudicated_common_name IS NULL)
    )
);

CREATE INDEX idx_ground_truth_adjudications_member_history
ON ground_truth_adjudications(
    ground_truth_member_id, created_at, ground_truth_adjudication_id
);

CREATE INDEX idx_ground_truth_adjudications_result_history
ON ground_truth_adjudications(result, created_at, ground_truth_adjudication_id);

CREATE INDEX idx_ground_truth_adjudications_taxon
ON ground_truth_adjudications(
    adjudicated_scientific_name, adjudicated_common_name, created_at
)
WHERE result IN ('CONFIRMED_TAXON', 'ALTERNATE_TAXON');

CREATE INDEX idx_ground_truth_adjudications_supersedes
ON ground_truth_adjudications(
    supersedes_adjudication_id, ground_truth_adjudication_id
)
WHERE supersedes_adjudication_id IS NOT NULL;

CREATE TRIGGER ground_truth_adjudications_supersession_same_member
BEFORE INSERT ON ground_truth_adjudications
WHEN NEW.supersedes_adjudication_id IS NOT NULL
 AND NOT EXISTS (
    SELECT 1 FROM ground_truth_adjudications AS prior
    WHERE prior.ground_truth_adjudication_id = NEW.supersedes_adjudication_id
      AND prior.ground_truth_member_id = NEW.ground_truth_member_id
)
BEGIN
    SELECT RAISE(ABORT, 'superseded adjudication must belong to the same member');
END;

CREATE TRIGGER ground_truth_adjudications_supersession_no_cycle
BEFORE INSERT ON ground_truth_adjudications
WHEN NEW.supersedes_adjudication_id IS NOT NULL
 AND NEW.ground_truth_adjudication_id IS NOT NULL
 AND EXISTS (
    WITH RECURSIVE ancestors(ground_truth_adjudication_id) AS (
        SELECT NEW.supersedes_adjudication_id
        UNION
        SELECT prior.supersedes_adjudication_id
        FROM ground_truth_adjudications AS prior
        JOIN ancestors
          ON prior.ground_truth_adjudication_id =
             ancestors.ground_truth_adjudication_id
        WHERE prior.supersedes_adjudication_id IS NOT NULL
    )
    SELECT 1 FROM ancestors
    WHERE ground_truth_adjudication_id = NEW.ground_truth_adjudication_id
)
BEGIN
    SELECT RAISE(ABORT, 'ground truth adjudication supersession cycle');
END;

CREATE TRIGGER ground_truth_adjudications_no_update
BEFORE UPDATE ON ground_truth_adjudications
BEGIN
    SELECT RAISE(ABORT, 'ground truth adjudications are append-only');
END;

CREATE TRIGGER ground_truth_adjudications_no_delete
BEFORE DELETE ON ground_truth_adjudications
BEGIN
    SELECT RAISE(ABORT, 'ground truth adjudications are append-only');
END;

CREATE TABLE ground_truth_adjudication_evidence (
    ground_truth_adjudication_evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ground_truth_adjudication_id INTEGER NOT NULL,
    evidence_id INTEGER NOT NULL,
    relationship_role TEXT NOT NULL CHECK (
        relationship_role IN ('PRIMARY', 'SUPPORTING', 'CONTEXT')
    ),
    created_at TEXT NOT NULL CHECK (length(trim(created_at)) > 0),
    FOREIGN KEY (ground_truth_adjudication_id)
        REFERENCES ground_truth_adjudications(ground_truth_adjudication_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (evidence_id)
        REFERENCES evidence(evidence_id) ON DELETE RESTRICT,
    UNIQUE (ground_truth_adjudication_id, evidence_id)
);

CREATE INDEX idx_ground_truth_adjudication_evidence_adjudication
ON ground_truth_adjudication_evidence(
    ground_truth_adjudication_id, ground_truth_adjudication_evidence_id
);

CREATE INDEX idx_ground_truth_adjudication_evidence_evidence
ON ground_truth_adjudication_evidence(evidence_id, ground_truth_adjudication_id);

CREATE TRIGGER ground_truth_adjudication_evidence_detection_compatible
BEFORE INSERT ON ground_truth_adjudication_evidence
WHEN NOT EXISTS (
    SELECT 1
    FROM ground_truth_adjudications AS adjudication
    JOIN ground_truth_members AS member
      ON member.ground_truth_member_id = adjudication.ground_truth_member_id
    JOIN assessments AS assessment
      ON assessment.assessment_id = member.assessment_id
    JOIN evidence AS item ON item.evidence_id = NEW.evidence_id
    WHERE adjudication.ground_truth_adjudication_id =
          NEW.ground_truth_adjudication_id
      AND assessment.detection_id = item.detection_id
)
BEGIN
    SELECT RAISE(ABORT, 'adjudication evidence must target the candidate detection');
END;

CREATE TRIGGER ground_truth_adjudication_evidence_no_update
BEFORE UPDATE ON ground_truth_adjudication_evidence
BEGIN
    SELECT RAISE(ABORT, 'ground truth adjudication evidence is append-only');
END;

CREATE TRIGGER ground_truth_adjudication_evidence_no_delete
BEFORE DELETE ON ground_truth_adjudication_evidence
BEGIN
    SELECT RAISE(ABORT, 'ground truth adjudication evidence is append-only');
END;
