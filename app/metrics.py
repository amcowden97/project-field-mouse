"""Small SQLite-backed operational metric helpers."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from time import monotonic
from typing import Iterator


def record_metric(
    connection: sqlite3.Connection,
    station_id: str,
    metric: str,
    value: float,
    unit: str,
    labels: dict | None = None,
) -> None:
    try:
        connection.execute(
            """INSERT INTO operational_metrics
            (station_id, metric, value, unit, recorded_at, labels)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (station_id, metric, value, unit, datetime.now(timezone.utc).isoformat(),
             json.dumps(labels or {}, sort_keys=True)),
        )
    except sqlite3.OperationalError as error:
        if "no such table" not in str(error):
            raise


@contextmanager
def measure(
    connection: sqlite3.Connection,
    station_id: str,
    metric: str,
    labels: dict | None = None,
) -> Iterator[None]:
    started = monotonic()
    try:
        yield
    finally:
        record_metric(
            connection, station_id, metric,
            (monotonic() - started) * 1000, "milliseconds", labels,
        )


def metrics_snapshot(connection: sqlite3.Connection) -> dict:
    page_count = connection.execute("PRAGMA page_count").fetchone()[0]
    page_size = connection.execute("PRAGMA page_size").fetchone()[0]
    database = page_count * page_size
    counts = connection.execute(
        """SELECT
        (SELECT COUNT(*) FROM recordings),
        (SELECT COUNT(*) FROM detections),
        (SELECT COUNT(*) FROM recordings WHERE processing_status = 'failed'),
        (SELECT COUNT(*) FROM recordings WHERE processing_status IN ('pending','processing')),
        (SELECT COUNT(*) FROM detections WHERE datetime(created_at) >= datetime('now','-1 day'))
        """
    ).fetchone()
    timings = {}
    try:
        rows = connection.execute(
            """SELECT metric, ROUND(AVG(value), 2), unit, COUNT(*)
            FROM operational_metrics WHERE datetime(recorded_at) >= datetime('now','-1 day')
            GROUP BY metric, unit"""
        )
        timings = {
            row[0]: {"average": row[1], "unit": row[2], "samples": row[3]} for row in rows
        }
    except sqlite3.OperationalError:
        pass
    return {
        "database_size_bytes": database,
        "recording_count": counts[0],
        "detection_count": counts[1],
        "failed_recordings": counts[2],
        "queue_depth": counts[3],
        "detections_last_24_hours": counts[4],
        "timings": timings,
    }
