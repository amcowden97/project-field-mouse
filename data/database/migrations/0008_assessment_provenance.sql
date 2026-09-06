PRAGMA foreign_keys = ON;

CREATE TABLE assessments (
    assessment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_identity TEXT NOT NULL UNIQUE
        CHECK (length(trim(assessment_identity)) BETWEEN 1 AND 200),
    payload_schema_version INTEGER NOT NULL DEFAULT 1
        CHECK (payload_schema_version >= 1),
    detection_id INTEGER NOT NULL,
    result TEXT NOT NULL CHECK (
        result IN ('SUPPORTED', 'NOT_SUPPORTED', 'INCONCLUSIVE', 'ALTERNATE_TAXON')
    ),
    assessed_scientific_name TEXT,
    assessed_common_name TEXT NOT NULL
        CHECK (length(trim(assessed_common_name)) > 0),
    alternate_scientific_name TEXT,
    alternate_common_name TEXT,
    reason_code TEXT NOT NULL CHECK (length(trim(reason_code)) BETWEEN 1 AND 100),
    reasoning TEXT NOT NULL CHECK (length(trim(reasoning)) BETWEEN 1 AND 4000),
    created_by TEXT NOT NULL CHECK (length(trim(created_by)) BETWEEN 1 AND 200),
    supersedes_assessment_id INTEGER,
    input_fingerprint TEXT NOT NULL UNIQUE CHECK (length(input_fingerprint) = 64),
    idempotency_key TEXT NOT NULL UNIQUE
        CHECK (length(trim(idempotency_key)) BETWEEN 1 AND 200),
    created_at TEXT NOT NULL CHECK (length(trim(created_at)) > 0),
    FOREIGN KEY (detection_id) REFERENCES detections(id) ON DELETE RESTRICT,
    FOREIGN KEY (supersedes_assessment_id)
        REFERENCES assessments(assessment_id) ON DELETE RESTRICT,
    CHECK (
        supersedes_assessment_id IS NULL
        OR supersedes_assessment_id != assessment_id
    ),
    CHECK (
        (result = 'ALTERNATE_TAXON' AND (
            length(trim(coalesce(alternate_scientific_name, ''))) > 0
            OR length(trim(coalesce(alternate_common_name, ''))) > 0
        ))
        OR (result != 'ALTERNATE_TAXON'
            AND alternate_scientific_name IS NULL
            AND alternate_common_name IS NULL)
    )
);

CREATE INDEX idx_assessments_detection_history
ON assessments(detection_id, created_at, assessment_id);

CREATE INDEX idx_assessments_result_history
ON assessments(result, created_at, assessment_id);

CREATE INDEX idx_assessments_assessed_taxon
ON assessments(assessed_scientific_name, assessed_common_name, created_at);

CREATE INDEX idx_assessments_alternate_taxon
ON assessments(alternate_scientific_name, alternate_common_name, created_at)
WHERE result = 'ALTERNATE_TAXON';

CREATE INDEX idx_assessments_supersedes
ON assessments(supersedes_assessment_id, assessment_id)
WHERE supersedes_assessment_id IS NOT NULL;

CREATE TRIGGER assessments_detection_claim_immutable
BEFORE INSERT ON assessments
WHEN NOT EXISTS (
    SELECT 1 FROM detections AS detection
    WHERE detection.id = NEW.detection_id
      AND detection.scientific_name IS NEW.assessed_scientific_name
      AND detection.common_name = NEW.assessed_common_name
)
BEGIN
    SELECT RAISE(ABORT, 'assessment claim must match the historical detection');
END;

CREATE TRIGGER assessments_supersession_same_detection
BEFORE INSERT ON assessments
WHEN NEW.supersedes_assessment_id IS NOT NULL
 AND NOT EXISTS (
    SELECT 1 FROM assessments AS prior
    WHERE prior.assessment_id = NEW.supersedes_assessment_id
      AND prior.detection_id = NEW.detection_id
)
BEGIN
    SELECT RAISE(ABORT, 'superseded assessment must target the same detection');
END;

CREATE TRIGGER assessments_supersession_no_cycle
BEFORE INSERT ON assessments
WHEN NEW.supersedes_assessment_id IS NOT NULL
 AND NEW.assessment_id IS NOT NULL
 AND EXISTS (
    WITH RECURSIVE ancestors(assessment_id) AS (
        SELECT NEW.supersedes_assessment_id
        UNION
        SELECT prior.supersedes_assessment_id
        FROM assessments AS prior
        JOIN ancestors ON prior.assessment_id = ancestors.assessment_id
        WHERE prior.supersedes_assessment_id IS NOT NULL
    )
    SELECT 1 FROM ancestors WHERE assessment_id = NEW.assessment_id
)
BEGIN
    SELECT RAISE(ABORT, 'assessment supersession cycle');
END;

CREATE TRIGGER assessments_no_update
BEFORE UPDATE ON assessments
BEGIN
    SELECT RAISE(ABORT, 'assessments are append-only');
END;

CREATE TRIGGER assessments_no_delete
BEFORE DELETE ON assessments
BEGIN
    SELECT RAISE(ABORT, 'assessments are append-only');
END;

CREATE TABLE assessment_evidence (
    assessment_evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id INTEGER NOT NULL,
    evidence_id INTEGER NOT NULL,
    created_at TEXT NOT NULL CHECK (length(trim(created_at)) > 0),
    FOREIGN KEY (assessment_id)
        REFERENCES assessments(assessment_id) ON DELETE RESTRICT,
    FOREIGN KEY (evidence_id) REFERENCES evidence(evidence_id) ON DELETE RESTRICT,
    UNIQUE (assessment_id, evidence_id)
);

CREATE INDEX idx_assessment_evidence_assessment
ON assessment_evidence(assessment_id, assessment_evidence_id);

CREATE INDEX idx_assessment_evidence_evidence
ON assessment_evidence(evidence_id, assessment_id);

CREATE TRIGGER assessment_evidence_detection_compatible
BEFORE INSERT ON assessment_evidence
WHEN NOT EXISTS (
    SELECT 1
    FROM assessments AS assessment
    JOIN evidence AS item ON item.evidence_id = NEW.evidence_id
    WHERE assessment.assessment_id = NEW.assessment_id
      AND assessment.detection_id = item.detection_id
)
BEGIN
    SELECT RAISE(ABORT, 'assessment evidence must target the same detection');
END;

CREATE TRIGGER assessment_evidence_no_update
BEFORE UPDATE ON assessment_evidence
BEGIN
    SELECT RAISE(ABORT, 'assessment evidence is append-only');
END;

CREATE TRIGGER assessment_evidence_no_delete
BEFORE DELETE ON assessment_evidence
BEGIN
    SELECT RAISE(ABORT, 'assessment evidence is append-only');
END;
