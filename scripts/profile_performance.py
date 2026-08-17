"""Reproducible SQLite and Flask performance profile for Project Field Mouse.

The profiler uses generated data in a temporary directory and never opens the
configured station database. Run it from the repository root:

    python scripts/profile_performance.py --detections 1000 10000 100000
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import statistics
import tempfile
import time
import tracemalloc
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import psutil

from app.database.connection import initialize_database
from app.web import app as web


SPECIES = (
    ("American Robin", "Turdus migratorius"),
    ("Song Sparrow", "Melospiza melodia"),
    ("Black-capped Chickadee", "Poecile atricapillus"),
    ("American Goldfinch", "Spinus tristis"),
    ("Northern Flicker", "Colaptes auratus"),
    ("Great Horned Owl", "Bubo virginianus"),
    ("House Finch", "Haemorhous mexicanus"),
    ("Dark-eyed Junco", "Junco hyemalis"),
)

ROUTES = (
    "/",
    "/activity",
    "/activity?page=100&per_page=20",
    "/life-list",
    "/species/American%20Robin",
    "/device",
    "/api/dashboard",
    "/api/metrics",
    "/audio/1",
    "/static/css/dashboard-v3.css",
)


class TracedConnection(sqlite3.Connection):
    query_count = 0


def connect_traced(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, factory=TracedConnection)
    connection.row_factory = sqlite3.Row
    connection.set_trace_callback(
        lambda statement: setattr(
            TracedConnection,
            "query_count",
            TracedConnection.query_count + (not statement.startswith("PRAGMA")),
        )
    )
    return connection


def populate(
    path: Path,
    recording_root: Path,
    detection_count: int,
    *,
    without_time_indexes: bool = False,
) -> float:
    initialize_database(path)
    recording_count = max(1, (detection_count + 9) // 10)
    now = datetime.now(timezone.utc)
    with sqlite3.connect(path) as connection:
        if without_time_indexes:
            connection.execute("DROP INDEX idx_detections_created")
            connection.execute("DROP INDEX idx_detections_datetime_created")
        started = time.perf_counter()
        connection.execute(
            "INSERT INTO stations (id, name, timezone, created_at) VALUES (?, ?, ?, ?)",
            ("audit-station", "Audit Station", "UTC", now.isoformat()),
        )
        recordings = []
        for index in range(recording_count):
            recorded = now - timedelta(minutes=recording_count - index)
            recordings.append((
                "audit-station",
                str(recording_root / f"recording-{index + 1}.wav"),
                recorded.isoformat(),
                60,
                48_000,
                1,
                "S16_LE",
                5_760_044,
                "processed",
                recorded.isoformat(),
            ))
        connection.executemany(
            """INSERT INTO recordings
               (station_id, file_path, recorded_at, duration_seconds, sample_rate,
                channels, sample_format, file_size_bytes, processing_status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            recordings,
        )
        batch = []
        for index in range(detection_count):
            common, scientific = SPECIES[index % len(SPECIES)]
            created = now - timedelta(seconds=(detection_count - index) * 30)
            batch.append((
                (index % recording_count) + 1,
                "birdnet",
                common,
                scientific,
                0.60 + ((index % 40) / 100),
                float(index % 55),
                float(index % 55) + 3,
                created.isoformat(),
            ))
            if len(batch) == 5_000:
                connection.executemany(
                    """INSERT INTO detections
                       (recording_id, detector, common_name, scientific_name,
                        confidence, start_time, end_time, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    batch,
                )
                batch.clear()
        if batch:
            connection.executemany(
                """INSERT INTO detections
                   (recording_id, detector, common_name, scientific_name,
                    confidence, start_time, end_time, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                batch,
            )
        connection.execute("ANALYZE")
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return (time.perf_counter() - started) * 1_000


@contextmanager
def configured_app(path: Path, recording_root: Path) -> Iterator[None]:
    original_path = web.DATABASE_PATH
    original_root = web.RECORDINGS_ROOT
    original_get_database = web.get_database
    web.DATABASE_PATH = path
    web.RECORDINGS_ROOT = recording_root.resolve()
    web.get_database = lambda: connect_traced(path)
    try:
        yield
    finally:
        web.DATABASE_PATH = original_path
        web.RECORDINGS_ROOT = original_root
        web.get_database = original_get_database


def profile_route(client, route: str, repetitions: int) -> dict:
    client.get(route)  # warm template, filesystem, and SQLite caches
    durations = []
    query_counts = []
    statuses = []
    response_bytes = 0
    peak_bytes = 0
    for _ in range(repetitions):
        TracedConnection.query_count = 0
        tracemalloc.start()
        started = time.perf_counter_ns()
        response = client.get(route)
        durations.append((time.perf_counter_ns() - started) / 1_000_000)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_bytes = max(peak_bytes, peak)
        query_counts.append(TracedConnection.query_count)
        statuses.append(response.status_code)
        response_bytes = len(response.data)
    return {
        "status": max(statuses),
        "median_ms": round(statistics.median(durations), 3),
        "p95_ms": round(sorted(durations)[max(
            0, math.ceil(len(durations) * 0.95) - 1
        )], 3),
        "queries": max(query_counts),
        "response_bytes": response_bytes,
        "peak_python_bytes": peak_bytes,
    }


def query_plans(path: Path) -> dict[str, list[str]]:
    statements = {
        "recent_detection": (
            "SELECT * FROM detections ORDER BY created_at DESC LIMIT 20",
            (),
        ),
        "recent_24h_wrapped": (
            "SELECT COUNT(*) FROM detections "
            "WHERE datetime(created_at) >= datetime('now', '-1 day')",
            (),
        ),
        "activity_page": (
            "SELECT id FROM detections WHERE confidence >= ? "
            "ORDER BY created_at DESC, confidence DESC LIMIT 20 OFFSET 1980",
            (0.8,),
        ),
        "species_page": (
            "SELECT id FROM detections WHERE common_name = ? AND confidence >= ? "
            "ORDER BY created_at DESC LIMIT 250",
            ("American Robin", 0.8),
        ),
    }
    with sqlite3.connect(path) as connection:
        return {
            name: [row[3] for row in connection.execute(
                "EXPLAIN QUERY PLAN " + sql, parameters
            )]
            for name, (sql, parameters) in statements.items()
        }


def profile_size(
    root: Path,
    detection_count: int,
    repetitions: int,
    *,
    without_time_indexes: bool,
) -> dict:
    database = root / f"fieldmouse-{detection_count}.db"
    recordings = root / "recordings"
    recordings.mkdir(exist_ok=True)
    # A minimal valid WAV-like payload is enough for conditional/range delivery.
    (recordings / "recording-1.wav").write_bytes(b"RIFF" + b"\0" * 4092)
    populate_ms = populate(
        database,
        recordings,
        detection_count,
        without_time_indexes=without_time_indexes,
    )
    process = psutil.Process(os.getpid())
    with configured_app(database, recordings):
        client = web.app.test_client()
        route_results = {
            route: profile_route(client, route, repetitions) for route in ROUTES
        }
    return {
        "detections": detection_count,
        "recordings": max(1, (detection_count + 9) // 10),
        "database_bytes": database.stat().st_size,
        "populate_ms": round(populate_ms, 3),
        "process_rss_bytes": process.memory_info().rss,
        "routes": route_results,
        "query_plans": query_plans(database),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--detections", nargs="+", type=int, default=[1_000, 10_000, 100_000])
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--without-time-indexes", action="store_true")
    arguments = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="fieldmouse-audit-") as directory:
        root = Path(directory)
        results = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "platform": dict(zip(
                ("system", "node", "release", "version", "machine"),
                os.uname(),
            )),
            "sqlite_version": sqlite3.sqlite_version,
            "repetitions": arguments.repetitions,
            "datasets": [
                profile_size(
                    root,
                    count,
                    arguments.repetitions,
                    without_time_indexes=arguments.without_time_indexes,
                )
                for count in arguments.detections
            ],
        }
    rendered = json.dumps(results, indent=2)
    if arguments.output:
        arguments.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
