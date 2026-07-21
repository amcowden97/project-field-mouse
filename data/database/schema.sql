PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS stations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    timezone TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recordings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id TEXT NOT NULL,
    file_path TEXT NOT NULL UNIQUE,
    recorded_at TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    sample_rate INTEGER NOT NULL,
    channels INTEGER NOT NULL,
    sample_format TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    processing_status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    FOREIGN KEY (station_id) REFERENCES stations(id)
);

CREATE INDEX IF NOT EXISTS idx_recordings_station_id
ON recordings(station_id);

CREATE INDEX IF NOT EXISTS idx_recordings_recorded_at
ON recordings(recorded_at);

CREATE INDEX IF NOT EXISTS idx_recordings_processing_status
ON recordings(processing_status);
