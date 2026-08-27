-- Dashboard and metrics routes order detections globally by timestamp and use
-- SQLite's datetime() normalization for mixed legacy/ISO timestamp formats.
CREATE INDEX IF NOT EXISTS idx_detections_created
ON detections(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_detections_datetime_created
ON detections(datetime(created_at));
