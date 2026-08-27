PRAGMA foreign_keys = ON;

ALTER TABLE recordings ADD COLUMN recording_identity TEXT;
ALTER TABLE recordings ADD COLUMN source_availability TEXT NOT NULL DEFAULT 'MISSING'
CHECK (source_availability IN ('AVAILABLE', 'INTENTIONALLY_EXPIRED', 'MISSING'));
ALTER TABLE recordings ADD COLUMN media_type TEXT NOT NULL DEFAULT 'audio/wav';
ALTER TABLE recordings ADD COLUMN source_sha256 TEXT
CHECK (source_sha256 IS NULL OR length(source_sha256) = 64);
ALTER TABLE recordings ADD COLUMN source_last_verified_at TEXT;

CREATE UNIQUE INDEX idx_recordings_identity
ON recordings(recording_identity)
WHERE recording_identity IS NOT NULL;

CREATE INDEX idx_recordings_source_availability
ON recordings(source_availability, recorded_at DESC);

CREATE TRIGGER recordings_assign_identity
AFTER INSERT ON recordings
WHEN NEW.recording_identity IS NULL OR trim(NEW.recording_identity) = ''
BEGIN
    UPDATE recordings
    SET recording_identity = NEW.station_id || ':' || printf('%020d', NEW.id)
    WHERE id = NEW.id;
END;

CREATE TRIGGER recordings_identity_immutable
BEFORE UPDATE OF recording_identity ON recordings
WHEN OLD.recording_identity IS NOT NULL
 AND NEW.recording_identity IS NOT OLD.recording_identity
BEGIN
    SELECT RAISE(ABORT, 'recording identity is immutable');
END;

CREATE TABLE recording_source_events (
    source_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id INTEGER NOT NULL,
    from_availability TEXT CHECK (
        from_availability IS NULL OR from_availability IN (
            'AVAILABLE', 'INTENTIONALLY_EXPIRED', 'MISSING'
        )
    ),
    to_availability TEXT NOT NULL CHECK (
        to_availability IN ('AVAILABLE', 'INTENTIONALLY_EXPIRED', 'MISSING')
    ),
    reason_code TEXT NOT NULL CHECK (length(trim(reason_code)) BETWEEN 1 AND 100),
    authorized_by TEXT NOT NULL CHECK (length(trim(authorized_by)) BETWEEN 1 AND 200),
    authorization_reference TEXT NOT NULL
        CHECK (length(trim(authorization_reference)) BETWEEN 1 AND 500),
    operation_id TEXT NOT NULL UNIQUE CHECK (length(trim(operation_id)) BETWEEN 1 AND 200),
    occurred_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata_json)),
    FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE RESTRICT,
    CHECK (
        to_availability != 'INTENTIONALLY_EXPIRED'
        OR (
            length(trim(reason_code)) > 0
            AND length(trim(authorized_by)) > 0
            AND length(trim(authorization_reference)) > 0
        )
    )
);

CREATE INDEX idx_recording_source_events_recording_time
ON recording_source_events(recording_id, occurred_at, source_event_id);

CREATE INDEX idx_recording_source_events_destination
ON recording_source_events(to_availability, occurred_at, source_event_id);

CREATE TRIGGER recording_source_events_no_update
BEFORE UPDATE ON recording_source_events
BEGIN
    SELECT RAISE(ABORT, 'recording source events are append-only');
END;

CREATE TRIGGER recording_source_events_no_delete
BEFORE DELETE ON recording_source_events
BEGIN
    SELECT RAISE(ABORT, 'recording source events are append-only');
END;

CREATE TABLE evidence (
    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_identity TEXT NOT NULL UNIQUE,
    detection_id INTEGER NOT NULL,
    payload_schema_version INTEGER NOT NULL DEFAULT 1
        CHECK (payload_schema_version >= 1),
    family TEXT NOT NULL CHECK (
        family IN (
            'MODEL', 'CONTEXTUAL', 'HISTORICAL', 'QUALITY',
            'HUMAN', 'EXPERT', 'DERIVED'
        )
    ),
    evidence_type TEXT NOT NULL CHECK (
        evidence_type IN (
            'MODEL_PREDICTION', 'MODEL_ALTERNATIVE',
            'MULTI_MODEL_AGREEMENT', 'MODEL_DISAGREEMENT',
            'STATION_HISTORY', 'HISTORICAL_MODEL_AGREEMENT',
            'HISTORICAL_HUMAN_SUPPORT', 'TEMPORAL_EVIDENCE',
            'HABITAT_EVIDENCE', 'GEOGRAPHIC_EVIDENCE',
            'AUDIO_QUALITY', 'HUMAN_CONFIRMATION', 'HUMAN_REJECTION',
            'HUMAN_UNSURE', 'HUMAN_ALTERNATE_IDENTIFICATION',
            'EXPERT_CONFIRMATION', 'EXPERT_REJECTION', 'EXPERT_UNSURE',
            'EXPERT_ALTERNATE_IDENTIFICATION', 'DERIVED_ASSERTION'
        )
    ),
    stance TEXT NOT NULL CHECK (
        stance IN ('SUPPORTS', 'CHALLENGES', 'NEUTRAL', 'INCONCLUSIVE')
    ),
    claimed_scientific_name TEXT,
    claimed_common_name TEXT,
    source_type TEXT NOT NULL CHECK (length(trim(source_type)) BETWEEN 1 AND 100),
    source_id TEXT NOT NULL CHECK (length(trim(source_id)) BETWEEN 1 AND 200),
    source_version TEXT NOT NULL CHECK (length(trim(source_version)) BETWEEN 1 AND 100),
    algorithm_version TEXT,
    confidence_value REAL CHECK (
        confidence_value IS NULL OR confidence_value BETWEEN 0 AND 1
    ),
    confidence_semantics TEXT,
    reason_code TEXT NOT NULL CHECK (length(trim(reason_code)) BETWEEN 1 AND 100),
    reasoning TEXT NOT NULL CHECK (length(trim(reasoning)) BETWEEN 1 AND 2000),
    metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (
        json_valid(metadata_json) AND length(metadata_json) <= 16384
    ),
    reviewer_id TEXT,
    reviewer_role TEXT CHECK (
        reviewer_role IS NULL OR reviewer_role IN ('HUMAN', 'EXPERT')
    ),
    observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    FOREIGN KEY (detection_id) REFERENCES detections(id) ON DELETE RESTRICT,
    CHECK (
        (confidence_value IS NULL AND confidence_semantics IS NULL)
        OR (
            confidence_value IS NOT NULL
            AND confidence_semantics IS NOT NULL
            AND length(trim(confidence_semantics)) > 0
        )
    ),
    CHECK (
        (family = 'MODEL' AND evidence_type IN (
            'MODEL_PREDICTION', 'MODEL_ALTERNATIVE',
            'MULTI_MODEL_AGREEMENT', 'MODEL_DISAGREEMENT'
        ))
        OR (family = 'CONTEXTUAL' AND evidence_type IN (
            'TEMPORAL_EVIDENCE', 'HABITAT_EVIDENCE', 'GEOGRAPHIC_EVIDENCE'
        ))
        OR (family = 'HISTORICAL' AND evidence_type IN (
            'STATION_HISTORY', 'HISTORICAL_MODEL_AGREEMENT',
            'HISTORICAL_HUMAN_SUPPORT'
        ))
        OR (family = 'QUALITY' AND evidence_type = 'AUDIO_QUALITY')
        OR (family = 'HUMAN' AND evidence_type IN (
            'HUMAN_CONFIRMATION', 'HUMAN_REJECTION', 'HUMAN_UNSURE',
            'HUMAN_ALTERNATE_IDENTIFICATION'
        ))
        OR (family = 'EXPERT' AND evidence_type IN (
            'EXPERT_CONFIRMATION', 'EXPERT_REJECTION', 'EXPERT_UNSURE',
            'EXPERT_ALTERNATE_IDENTIFICATION'
        ))
        OR (family = 'DERIVED' AND evidence_type = 'DERIVED_ASSERTION')
    ),
    CHECK (
        (family IN ('HUMAN', 'EXPERT') AND reviewer_id IS NOT NULL
            AND reviewer_role = family)
        OR (family NOT IN ('HUMAN', 'EXPERT') AND reviewer_id IS NULL
            AND reviewer_role IS NULL)
    )
);

CREATE INDEX idx_evidence_detection_created
ON evidence(detection_id, created_at, evidence_id);

CREATE INDEX idx_evidence_claim
ON evidence(claimed_scientific_name, family, evidence_type, created_at, evidence_id);

CREATE INDEX idx_evidence_source_identity
ON evidence(source_type, source_id, source_version);

CREATE TRIGGER evidence_no_update
BEFORE UPDATE ON evidence
BEGIN
    SELECT RAISE(ABORT, 'evidence is append-only');
END;

CREATE TRIGGER evidence_no_delete
BEFORE DELETE ON evidence
BEGIN
    SELECT RAISE(ABORT, 'evidence is append-only');
END;

CREATE TABLE evidence_lineage (
    child_evidence_id INTEGER NOT NULL,
    parent_evidence_id INTEGER NOT NULL,
    relationship TEXT NOT NULL CHECK (
        relationship IN ('DERIVED_FROM', 'SUPERSEDES', 'CORROBORATES', 'CHALLENGES')
    ),
    created_at TEXT NOT NULL,
    PRIMARY KEY (child_evidence_id, parent_evidence_id, relationship),
    FOREIGN KEY (child_evidence_id) REFERENCES evidence(evidence_id) ON DELETE RESTRICT,
    FOREIGN KEY (parent_evidence_id) REFERENCES evidence(evidence_id) ON DELETE RESTRICT,
    CHECK (child_evidence_id != parent_evidence_id)
);

CREATE INDEX idx_evidence_lineage_parent
ON evidence_lineage(parent_evidence_id, child_evidence_id);

CREATE TRIGGER evidence_lineage_no_cycle
BEFORE INSERT ON evidence_lineage
WHEN EXISTS (
    WITH RECURSIVE descendants(evidence_id) AS (
        SELECT child_evidence_id
        FROM evidence_lineage
        WHERE parent_evidence_id = NEW.child_evidence_id
        UNION
        SELECT edge.child_evidence_id
        FROM evidence_lineage AS edge
        JOIN descendants ON edge.parent_evidence_id = descendants.evidence_id
    )
    SELECT 1 FROM descendants WHERE evidence_id = NEW.parent_evidence_id
)
BEGIN
    SELECT RAISE(ABORT, 'evidence lineage cycle');
END;

CREATE TRIGGER evidence_lineage_no_update
BEFORE UPDATE ON evidence_lineage
BEGIN
    SELECT RAISE(ABORT, 'evidence lineage is append-only');
END;

CREATE TRIGGER evidence_lineage_no_delete
BEFORE DELETE ON evidence_lineage
BEGIN
    SELECT RAISE(ABORT, 'evidence lineage is append-only');
END;

CREATE TABLE evidence_sources (
    evidence_source_id INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id INTEGER NOT NULL,
    recording_id INTEGER NOT NULL,
    source_role TEXT NOT NULL CHECK (
        source_role IN ('PRIMARY', 'SUPPORTING', 'CONTEXT')
    ),
    interval_start_seconds REAL,
    interval_end_seconds REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (evidence_id) REFERENCES evidence(evidence_id) ON DELETE RESTRICT,
    FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE RESTRICT,
    CHECK (
        (interval_start_seconds IS NULL AND interval_end_seconds IS NULL)
        OR (
            interval_start_seconds IS NOT NULL
            AND interval_end_seconds IS NOT NULL
            AND interval_start_seconds >= 0
            AND interval_end_seconds > interval_start_seconds
        )
    )
);

CREATE UNIQUE INDEX idx_evidence_sources_no_duplicates
ON evidence_sources(
    evidence_id,
    recording_id,
    source_role,
    ifnull(interval_start_seconds, -1),
    ifnull(interval_end_seconds, -1)
);

CREATE INDEX idx_evidence_sources_evidence
ON evidence_sources(evidence_id, evidence_source_id);

CREATE INDEX idx_evidence_sources_recording
ON evidence_sources(recording_id, evidence_id);

CREATE TRIGGER evidence_sources_interval_bound
BEFORE INSERT ON evidence_sources
WHEN NEW.interval_end_seconds IS NOT NULL
 AND NEW.interval_end_seconds > (
    SELECT duration_seconds FROM recordings WHERE id = NEW.recording_id
 )
BEGIN
    SELECT RAISE(ABORT, 'evidence source interval exceeds recording duration');
END;

CREATE TRIGGER evidence_sources_no_update
BEFORE UPDATE ON evidence_sources
BEGIN
    SELECT RAISE(ABORT, 'evidence sources are append-only');
END;

CREATE TRIGGER evidence_sources_no_delete
BEFORE DELETE ON evidence_sources
BEGIN
    SELECT RAISE(ABORT, 'evidence sources are append-only');
END;

CREATE TABLE recording_protections (
    protection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id INTEGER NOT NULL,
    protection_type TEXT NOT NULL CHECK (
        protection_type IN (
            'MANUALLY_PINNED', 'FIRST_CONFIRMED', 'VERIFICATION_EVIDENCE',
            'GROUND_TRUTH_EVIDENCE', 'SCIENTIFICALLY_INTERESTING',
            'RESEARCH_HOLD', 'SIGNIFICANT_OBSERVATION'
        )
    ),
    origin_type TEXT NOT NULL CHECK (
        origin_type IN (
            'MANUAL', 'EVIDENCE', 'REVIEW', 'OBSERVATION',
            'GROUND_TRUTH', 'RESEARCH', 'SYSTEM_POLICY'
        )
    ),
    origin_reference TEXT NOT NULL
        CHECK (length(trim(origin_reference)) BETWEEN 1 AND 500),
    origin_evidence_id INTEGER,
    reason_code TEXT NOT NULL CHECK (length(trim(reason_code)) BETWEEN 1 AND 100),
    reason TEXT NOT NULL CHECK (length(trim(reason)) BETWEEN 1 AND 1000),
    created_by TEXT NOT NULL CHECK (length(trim(created_by)) BETWEEN 1 AND 200),
    created_at TEXT NOT NULL,
    released_at TEXT,
    released_by TEXT,
    release_reason TEXT,
    FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE RESTRICT,
    FOREIGN KEY (origin_evidence_id) REFERENCES evidence(evidence_id) ON DELETE RESTRICT,
    CHECK (
        (origin_type = 'EVIDENCE' AND origin_evidence_id IS NOT NULL)
        OR (origin_type != 'EVIDENCE' AND origin_evidence_id IS NULL)
    ),
    CHECK (
        (released_at IS NULL AND released_by IS NULL AND release_reason IS NULL)
        OR (
            released_at IS NOT NULL
            AND released_by IS NOT NULL
            AND length(trim(released_by)) > 0
            AND release_reason IS NOT NULL
            AND length(trim(release_reason)) > 0
        )
    )
);

CREATE UNIQUE INDEX idx_recording_protections_active_unique
ON recording_protections(
    recording_id, protection_type, origin_type, origin_reference
)
WHERE released_at IS NULL;

CREATE INDEX idx_recording_protections_active_recording
ON recording_protections(recording_id, protection_type, protection_id)
WHERE released_at IS NULL;

CREATE INDEX idx_recording_protections_origin_evidence
ON recording_protections(origin_evidence_id)
WHERE origin_evidence_id IS NOT NULL;

CREATE TRIGGER recording_protections_no_delete
BEFORE DELETE ON recording_protections
BEGIN
    SELECT RAISE(ABORT, 'recording protection history cannot be deleted');
END;

CREATE TRIGGER recording_protections_release_only
BEFORE UPDATE ON recording_protections
WHEN NOT (
    OLD.released_at IS NULL
    AND NEW.released_at IS NOT NULL
    AND NEW.recording_id IS OLD.recording_id
    AND NEW.protection_type IS OLD.protection_type
    AND NEW.origin_type IS OLD.origin_type
    AND NEW.origin_reference IS OLD.origin_reference
    AND NEW.origin_evidence_id IS OLD.origin_evidence_id
    AND NEW.reason_code IS OLD.reason_code
    AND NEW.reason IS OLD.reason
    AND NEW.created_by IS OLD.created_by
    AND NEW.created_at IS OLD.created_at
)
BEGIN
    SELECT RAISE(ABORT, 'recording protections are immutable except for release');
END;

CREATE TRIGGER recordings_intentional_expiry_requires_provenance
BEFORE UPDATE OF source_availability ON recordings
WHEN NEW.source_availability = 'INTENTIONALLY_EXPIRED'
 AND OLD.source_availability != 'INTENTIONALLY_EXPIRED'
 AND NOT EXISTS (
    SELECT 1
    FROM recording_source_events AS event
    WHERE event.recording_id = NEW.id
      AND event.to_availability = 'INTENTIONALLY_EXPIRED'
      AND event.from_availability = OLD.source_availability
      AND event.source_event_id = (
          SELECT max(latest.source_event_id)
          FROM recording_source_events AS latest
          WHERE latest.recording_id = NEW.id
      )
 )
BEGIN
    SELECT RAISE(ABORT, 'intentional expiration requires provenance');
END;

CREATE TRIGGER recordings_protection_blocks_expiry
BEFORE UPDATE OF source_availability ON recordings
WHEN NEW.source_availability = 'INTENTIONALLY_EXPIRED'
 AND OLD.source_availability != 'INTENTIONALLY_EXPIRED'
 AND EXISTS (
    SELECT 1
    FROM recording_protections AS protection
    WHERE protection.recording_id = NEW.id
      AND protection.released_at IS NULL
 )
BEGIN
    SELECT RAISE(ABORT, 'active recording protection blocks expiration');
END;

CREATE TABLE evidence_schema_migration_runs (
    migration_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_version INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    total_recordings INTEGER NOT NULL,
    available_count INTEGER NOT NULL,
    intentionally_expired_count INTEGER NOT NULL,
    missing_count INTEGER NOT NULL,
    confident_expiration_count INTEGER NOT NULL,
    ambiguous_absent_count INTEGER NOT NULL,
    availability_backfill_ms REAL NOT NULL,
    index_creation_ms REAL NOT NULL,
    warnings_json TEXT NOT NULL CHECK (json_valid(warnings_json))
);
