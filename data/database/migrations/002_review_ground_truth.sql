ALTER TABLE verifications
ADD COLUMN evidence_json TEXT NOT NULL DEFAULT '[]';

ALTER TABLE verifications
ADD COLUMN review_priority INTEGER NOT NULL DEFAULT 0
CHECK (review_priority BETWEEN 0 AND 100);

ALTER TABLE verifications
ADD COLUMN review_flags_json TEXT NOT NULL DEFAULT '[]';

CREATE TABLE IF NOT EXISTS detection_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detection_id INTEGER NOT NULL,
    review_state TEXT NOT NULL CHECK (
        review_state IN (
            'pending_review',
            'verified',
            'rejected',
            'corrected_species',
            'ignored'
        )
    ),
    reviewed_at TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    original_scientific_name TEXT,
    original_common_name TEXT NOT NULL,
    corrected_scientific_name TEXT,
    corrected_common_name TEXT,
    notes TEXT NOT NULL DEFAULT '',
    confidence_before REAL NOT NULL CHECK (confidence_before BETWEEN 0 AND 1),
    confidence_after REAL CHECK (
        confidence_after IS NULL OR confidence_after BETWEEN 0 AND 1
    ),
    created_at TEXT NOT NULL,
    FOREIGN KEY (detection_id) REFERENCES detections(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_detection_reviews_detection
ON detection_reviews(detection_id, reviewed_at DESC);

CREATE INDEX IF NOT EXISTS idx_detection_reviews_state
ON detection_reviews(review_state, reviewed_at DESC);

CREATE VIEW IF NOT EXISTS latest_detection_reviews AS
SELECT review.*
FROM detection_reviews AS review
WHERE review.id = (
    SELECT candidate.id
    FROM detection_reviews AS candidate
    WHERE candidate.detection_id = review.detection_id
    ORDER BY candidate.reviewed_at DESC, candidate.id DESC
    LIMIT 1
);
