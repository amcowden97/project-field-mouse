PRAGMA foreign_keys = ON;

CREATE TABLE server_recording_ingestions (
    ingestion_id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id TEXT NOT NULL,
    station_uuid TEXT NOT NULL,
    recording_identity TEXT NOT NULL UNIQUE,
    recorded_at TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK (
        length(content_sha256) = 64
        AND content_sha256 = lower(content_sha256)
        AND content_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    file_size_bytes INTEGER NOT NULL CHECK (file_size_bytes > 0),
    duration_seconds REAL NOT NULL CHECK (duration_seconds > 0),
    sample_rate INTEGER NOT NULL CHECK (sample_rate > 0),
    channels INTEGER NOT NULL CHECK (channels > 0),
    sample_format TEXT NOT NULL CHECK (length(trim(sample_format)) BETWEEN 1 AND 32),
    media_type TEXT NOT NULL CHECK (length(trim(media_type)) BETWEEN 1 AND 100),
    state TEXT NOT NULL CHECK (state IN ('AWAITING_MEDIA', 'COMPLETED')),
    recording_id INTEGER,
    created_at TEXT NOT NULL,
    last_declared_at TEXT NOT NULL,
    declaration_count INTEGER NOT NULL DEFAULT 1 CHECK (declaration_count >= 1),
    completed_at TEXT,
    FOREIGN KEY (station_id) REFERENCES stations(id) ON DELETE RESTRICT,
    FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE RESTRICT,
    CHECK (
        (state = 'AWAITING_MEDIA' AND completed_at IS NULL)
        OR (
            state = 'COMPLETED'
            AND recording_id IS NOT NULL
            AND completed_at IS NOT NULL
        )
    )
);

CREATE UNIQUE INDEX idx_server_recording_ingestions_recording
ON server_recording_ingestions(recording_id)
WHERE recording_id IS NOT NULL;

CREATE INDEX idx_server_recording_ingestions_state_created
ON server_recording_ingestions(state, created_at, ingestion_id);

CREATE INDEX idx_server_recording_ingestions_station_last_declared
ON server_recording_ingestions(station_id, last_declared_at DESC, ingestion_id DESC);

CREATE TRIGGER server_recording_ingestions_station_consistent
BEFORE INSERT ON server_recording_ingestions
WHEN NOT EXISTS (
    SELECT 1 FROM stations AS station
    WHERE station.id = NEW.station_id
      AND station.station_uuid = NEW.station_uuid
)
BEGIN
    SELECT RAISE(ABORT, 'ingestion Station identity is inconsistent');
END;

CREATE TRIGGER server_recording_ingestions_recording_consistent_insert
BEFORE INSERT ON server_recording_ingestions
WHEN NEW.recording_id IS NOT NULL
 AND NOT EXISTS (
    SELECT 1 FROM recordings AS recording
    WHERE recording.id = NEW.recording_id
      AND recording.station_id = NEW.station_id
      AND recording.recording_identity = NEW.recording_identity
)
BEGIN
    SELECT RAISE(ABORT, 'ingestion Recording identity is inconsistent');
END;

CREATE TRIGGER server_recording_ingestions_recording_consistent_update
BEFORE UPDATE OF recording_id ON server_recording_ingestions
WHEN NEW.recording_id IS NOT NULL
 AND NOT EXISTS (
    SELECT 1 FROM recordings AS recording
    WHERE recording.id = NEW.recording_id
      AND recording.station_id = NEW.station_id
      AND recording.recording_identity = NEW.recording_identity
)
BEGIN
    SELECT RAISE(ABORT, 'ingestion Recording identity is inconsistent');
END;

CREATE TRIGGER server_recording_ingestions_declaration_immutable
BEFORE UPDATE ON server_recording_ingestions
WHEN NEW.station_id IS NOT OLD.station_id
 OR NEW.station_uuid IS NOT OLD.station_uuid
 OR NEW.recording_identity IS NOT OLD.recording_identity
 OR NEW.recorded_at IS NOT OLD.recorded_at
 OR NEW.content_sha256 IS NOT OLD.content_sha256
 OR NEW.file_size_bytes IS NOT OLD.file_size_bytes
 OR NEW.duration_seconds IS NOT OLD.duration_seconds
 OR NEW.sample_rate IS NOT OLD.sample_rate
 OR NEW.channels IS NOT OLD.channels
 OR NEW.sample_format IS NOT OLD.sample_format
 OR NEW.media_type IS NOT OLD.media_type
 OR NEW.created_at IS NOT OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'ingestion declaration is immutable');
END;

CREATE TRIGGER server_recording_ingestions_mapping_immutable
BEFORE UPDATE OF recording_id ON server_recording_ingestions
WHEN OLD.recording_id IS NOT NULL
 AND NEW.recording_id IS NOT OLD.recording_id
BEGIN
    SELECT RAISE(ABORT, 'ingestion Recording mapping is immutable once assigned');
END;

CREATE TRIGGER server_recording_ingestions_no_reverse_transition
BEFORE UPDATE OF state ON server_recording_ingestions
WHEN OLD.state = 'COMPLETED' AND NEW.state != 'COMPLETED'
BEGIN
    SELECT RAISE(ABORT, 'completed ingestion cannot return to awaiting media');
END;

CREATE TRIGGER server_recording_ingestions_completion_immutable
BEFORE UPDATE OF completed_at ON server_recording_ingestions
WHEN OLD.completed_at IS NOT NULL
 AND NEW.completed_at IS NOT OLD.completed_at
BEGIN
    SELECT RAISE(ABORT, 'ingestion completion time is immutable');
END;

CREATE TRIGGER server_recording_ingestions_no_delete
BEFORE DELETE ON server_recording_ingestions
BEGIN
    SELECT RAISE(ABORT, 'server ingestion history cannot be deleted');
END;
