PRAGMA foreign_keys = ON;

ALTER TABLE recordings ADD COLUMN content_sha256 TEXT
CHECK (
    content_sha256 IS NULL
    OR (
        length(content_sha256) = 64
        AND content_sha256 = lower(content_sha256)
        AND content_sha256 NOT GLOB '*[^0-9a-f]*'
    )
);

-- Migration 0006 assigned a local station-id/database-id value.  The Python
-- migration callback replaces historical values with stable UUIDs before
-- recreating both triggers with distributed-identity semantics.
DROP TRIGGER recordings_assign_identity;
DROP TRIGGER recordings_identity_immutable;

CREATE TRIGGER recordings_content_sha256_immutable
BEFORE UPDATE OF content_sha256 ON recordings
WHEN OLD.content_sha256 IS NOT NEW.content_sha256
BEGIN
    SELECT RAISE(ABORT, 'recording content SHA-256 is immutable');
END;

CREATE TABLE station_sync_outbox (
    outbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id INTEGER NOT NULL UNIQUE,
    recording_identity TEXT NOT NULL UNIQUE,
    station_uuid TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'PENDING' CHECK (
        state IN (
            'PENDING', 'ACKNOWLEDGED',
            'FAILED_RETRYABLE', 'FAILED_PERMANENT'
        )
    ),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_attempt_at TEXT,
    last_error TEXT,
    server_acknowledged_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE RESTRICT,
    CHECK (length(trim(recording_identity)) > 0),
    CHECK (length(trim(station_uuid)) > 0),
    CHECK (
        (state = 'ACKNOWLEDGED' AND server_acknowledged_at IS NOT NULL)
        OR (state != 'ACKNOWLEDGED' AND server_acknowledged_at IS NULL)
    )
);

CREATE INDEX idx_station_sync_outbox_state_created
ON station_sync_outbox(state, created_at, outbox_id);

CREATE TRIGGER station_sync_outbox_identity_consistent
BEFORE INSERT ON station_sync_outbox
WHEN NOT EXISTS (
    SELECT 1
    FROM recordings AS recording
    JOIN stations AS station ON station.id = recording.station_id
    WHERE recording.id = NEW.recording_id
      AND recording.recording_identity = NEW.recording_identity
      AND station.station_uuid = NEW.station_uuid
)
BEGIN
    SELECT RAISE(ABORT, 'outbox identity does not match recording and station');
END;

CREATE TRIGGER station_sync_outbox_identity_immutable
BEFORE UPDATE ON station_sync_outbox
WHEN NEW.recording_id IS NOT OLD.recording_id
 OR NEW.recording_identity IS NOT OLD.recording_identity
 OR NEW.station_uuid IS NOT OLD.station_uuid
 OR NEW.created_at IS NOT OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'outbox identity fields are immutable');
END;

CREATE TRIGGER station_sync_outbox_no_delete
BEFORE DELETE ON station_sync_outbox
BEGIN
    SELECT RAISE(ABORT, 'station synchronization intent cannot be deleted');
END;

CREATE TABLE station_sync_migration_runs (
    migration_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_version INTEGER NOT NULL,
    station_uuids_assigned INTEGER NOT NULL,
    recording_identities_assigned INTEGER NOT NULL,
    historical_checksums_populated INTEGER NOT NULL,
    historical_checksums_left_null INTEGER NOT NULL,
    elapsed_ms REAL NOT NULL,
    completed_at TEXT NOT NULL
);
