ALTER TABLE stations ADD COLUMN station_uuid TEXT;
ALTER TABLE stations ADD COLUMN hardware_version TEXT;
ALTER TABLE stations ADD COLUMN software_version TEXT;
ALTER TABLE stations ADD COLUMN deployment_date TEXT;
ALTER TABLE stations ADD COLUMN location_name TEXT;
ALTER TABLE stations ADD COLUMN latitude REAL;
ALTER TABLE stations ADD COLUMN longitude REAL;
ALTER TABLE stations ADD COLUMN capabilities TEXT NOT NULL DEFAULT '[]';
CREATE UNIQUE INDEX IF NOT EXISTS idx_stations_uuid
ON stations(station_uuid) WHERE station_uuid IS NOT NULL;
CREATE TABLE IF NOT EXISTS operational_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    labels TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (station_id) REFERENCES stations(id)
);
CREATE INDEX IF NOT EXISTS idx_metrics_station_name_time
ON operational_metrics(station_id, metric, recorded_at DESC);
