PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id INTEGER NOT NULL,
    detector TEXT NOT NULL,
    scientific_name TEXT,
    common_name TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    start_time REAL,
    end_time REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_detections_recording_id
ON detections(recording_id);

CREATE INDEX IF NOT EXISTS idx_detections_species
ON detections(scientific_name, common_name);

CREATE TABLE IF NOT EXISTS verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detection_id INTEGER NOT NULL UNIQUE,
    consensus_score REAL NOT NULL CHECK (consensus_score BETWEEN 0 AND 1),
    status TEXT NOT NULL CHECK (
        status IN ('verified', 'probable', 'uncertain', 'rejected')
    ),
    reason TEXT NOT NULL,
    explanation_json TEXT NOT NULL,
    rule_action TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'unreviewed' CHECK (
        review_status IN ('unreviewed', 'confirmed', 'corrected', 'dismissed')
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (detection_id) REFERENCES detections(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_verifications_status
ON verifications(status, consensus_score);

CREATE TABLE IF NOT EXISTS verification_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    verification_id INTEGER NOT NULL,
    plugin_name TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK (
        verdict IN ('support', 'neutral', 'oppose')
    ),
    score REAL NOT NULL CHECK (score BETWEEN 0 AND 1),
    weight REAL NOT NULL CHECK (weight >= 0),
    reason TEXT NOT NULL,
    output_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (verification_id) REFERENCES verifications(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_verification_results_verification
ON verification_results(verification_id);
