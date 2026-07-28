from __future__ import annotations

import shutil
import socket
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = PROJECT_ROOT / "data" / "database" / "fieldmouse.db"
RECORDINGS_ROOT = (PROJECT_ROOT / "data" / "recordings").resolve()

app = Flask(__name__)


def get_database() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def resolve_recording_path(file_path: str) -> Path | None:
    path = (PROJECT_ROOT / file_path).resolve()

    if path != RECORDINGS_ROOT and RECORDINGS_ROOT not in path.parents:
        return None

    return path


def seconds_since(timestamp: str | None) -> float | None:
    if not timestamp:
        return None

    try:
        parsed = datetime.fromisoformat(timestamp)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return (
            datetime.now(timezone.utc)
            - parsed.astimezone(timezone.utc)
        ).total_seconds()

    except ValueError:
        return None


def get_dashboard_stats(connection: sqlite3.Connection) -> dict:
    detection_stats = connection.execute(
        """
        SELECT
            COUNT(*) AS total_detections,
            COUNT(DISTINCT common_name) AS species_count,
            ROUND(AVG(confidence) * 100, 1) AS average_confidence,
            MAX(created_at) AS latest_detection_at
        FROM detections
        """
    ).fetchone()

    recording_stats = connection.execute(
        """
        SELECT
            COUNT(*) AS total_recordings,
            COALESCE(SUM(file_size_bytes), 0) AS total_recording_bytes,
            MAX(recorded_at) AS latest_recording_at
        FROM recordings
        """
    ).fetchone()

    recent_stats = connection.execute(
        """
        SELECT
            COUNT(*) AS detections_last_24_hours,
            COUNT(DISTINCT common_name) AS species_last_24_hours
        FROM detections
        WHERE datetime(created_at) >= datetime('now', '-24 hours')
        """
    ).fetchone()

    disk = shutil.disk_usage(PROJECT_ROOT)

    latest_recording_at = recording_stats["latest_recording_at"]
    recording_age_seconds = seconds_since(latest_recording_at)

    recorder_recent = (
        recording_age_seconds is not None
        and recording_age_seconds <= 180
    )

    return {
        "hostname": socket.gethostname(),
        "total_detections": detection_stats["total_detections"] or 0,
        "species_count": detection_stats["species_count"] or 0,
        "average_confidence": detection_stats["average_confidence"] or 0,
        "latest_detection_at": detection_stats["latest_detection_at"],
        "total_recordings": recording_stats["total_recordings"] or 0,
        "total_recording_bytes": (
            recording_stats["total_recording_bytes"] or 0
        ),
        "latest_recording_at": latest_recording_at,
        "recorder_recent": recorder_recent,
        "recording_age_seconds": recording_age_seconds,
        "detections_last_24_hours": (
            recent_stats["detections_last_24_hours"] or 0
        ),
        "species_last_24_hours": (
            recent_stats["species_last_24_hours"] or 0
        ),
        "disk_total": disk.total,
        "disk_used": disk.used,
        "disk_free": disk.free,
        "disk_percent": round((disk.used / disk.total) * 100, 1),
    }


def get_top_species(
    connection: sqlite3.Connection,
    limit: int = 5,
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT
            common_name,
            scientific_name,
            COUNT(*) AS detection_count,
            ROUND(MAX(confidence) * 100, 1) AS highest_confidence,
            MAX(created_at) AS last_detected_at
        FROM detections
        WHERE datetime(created_at) >= datetime('now', '-24 hours')
        GROUP BY common_name, scientific_name
        ORDER BY detection_count DESC, highest_confidence DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def get_latest_detection(
    connection: sqlite3.Connection,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT
            d.id AS detection_id,
            d.recording_id,
            d.common_name,
            d.scientific_name,
            d.confidence,
            d.created_at,
            r.recorded_at,
            r.file_path
        FROM detections d
        JOIN recordings r ON r.id = d.recording_id
        ORDER BY d.created_at DESC
        LIMIT 1
        """
    ).fetchone()


def get_life_list_species(
    connection: sqlite3.Connection,
    sort_by: str = "recent",
) -> list[dict]:
    sort_options = {
        "recent": (
            "last_detected_at DESC, "
            "total_detections DESC, "
            "common_name COLLATE NOCASE"
        ),
        "first": (
            "first_detected_at ASC, "
            "common_name COLLATE NOCASE"
        ),
        "name": (
            "common_name COLLATE NOCASE ASC"
        ),
        "detections": (
            "total_detections DESC, "
            "last_detected_at DESC, "
            "common_name COLLATE NOCASE"
        ),
        "confidence": (
            "highest_confidence DESC, "
            "total_detections DESC, "
            "common_name COLLATE NOCASE"
        ),
    }

    order_clause = sort_options.get(
        sort_by,
        sort_options["recent"],
    )

    rows = connection.execute(
        f"""
        SELECT
            common_name,
            scientific_name,
            COUNT(*) AS total_detections,
            ROUND(AVG(confidence) * 100, 1)
                AS average_confidence,
            ROUND(MAX(confidence) * 100, 1)
                AS highest_confidence,
            MIN(created_at) AS first_detected_at,
            MAX(created_at) AS last_detected_at,
            COUNT(DISTINCT DATE(created_at))
                AS active_days
        FROM detections
        GROUP BY common_name, scientific_name
        ORDER BY {order_clause}
        """
    ).fetchall()

    species = []

    for index, row in enumerate(rows, start=1):
        item = dict(row)
        item["collection_number"] = index
        species.append(item)

    return species


def get_detection_rows(
    connection: sqlite3.Connection,
    minimum_confidence: float,
    limit: int,
    offset: int = 0,
) -> list[dict]:
    rows = connection.execute(
        """
        SELECT
            d.id AS detection_id,
            d.recording_id,
            d.common_name,
            d.scientific_name,
            d.confidence,
            d.start_time,
            d.end_time,
            d.created_at,
            r.recorded_at,
            r.file_path,
            r.duration_seconds
        FROM detections d
        JOIN recordings r ON r.id = d.recording_id
        WHERE d.confidence >= ?
        ORDER BY d.created_at DESC, d.confidence DESC
        LIMIT ? OFFSET ?
        """,
        (minimum_confidence, limit, offset),
    ).fetchall()

    detections = []

    for row in rows:
        detection = dict(row)

        recording_path = resolve_recording_path(
            detection["file_path"]
        )

        detection["audio_available"] = bool(
            recording_path
            and recording_path.is_file()
        )

        detections.append(detection)

    return detections


def get_detection_count(
    connection: sqlite3.Connection,
    minimum_confidence: float,
) -> int:
    row = connection.execute(
        """
        SELECT COUNT(*) AS result_count
        FROM detections
        WHERE confidence >= ?
        """,
        (minimum_confidence,),
    ).fetchone()

    return int(row["result_count"] or 0)


@app.template_filter("filesize")
def format_filesize(byte_count: int | float | None) -> str:
    if not byte_count:
        return "0 B"

    size = float(byte_count)

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"

        size /= 1024

    return f"{byte_count} B"


@app.route("/")
def index():
    try:
        minimum_confidence = float(
            request.args.get("min_confidence", "0.80")
        )
    except ValueError:
        minimum_confidence = 0.80

    minimum_confidence = max(
        0.0,
        min(minimum_confidence, 1.0),
    )

    try:
        limit = int(request.args.get("limit", "100"))
    except ValueError:
        limit = 100

    limit = max(10, min(limit, 500))

    with get_database() as connection:

        detections = get_detection_rows(
            connection,
            minimum_confidence=minimum_confidence,
            limit=min(limit, 6),
        )

        stats = get_dashboard_stats(connection)
        top_species = get_top_species(connection)
        latest_detection = get_latest_detection(connection)

        if latest_detection is not None:
            latest_detection = dict(latest_detection)

            latest_path = resolve_recording_path(
                latest_detection["file_path"]
            )

            latest_detection["audio_available"] = bool(
                latest_path
                and latest_path.is_file()
            )

    return render_template(
        "index.html",
        detections=detections,
        stats=stats,
        top_species=top_species,
        latest_detection=latest_detection,
        minimum_confidence=minimum_confidence,
        limit=limit,
    )


@app.route("/activity")
def activity():
    try:
        minimum_confidence = float(
            request.args.get("min_confidence", "0.80")
        )
    except ValueError:
        minimum_confidence = 0.80

    minimum_confidence = max(
        0.0,
        min(minimum_confidence, 1.0),
    )

    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        page = 1

    page = max(1, page)

    try:
        per_page = int(request.args.get("per_page", "20"))
    except ValueError:
        per_page = 20

    per_page = max(10, min(per_page, 100))
    offset = (page - 1) * per_page

    with get_database() as connection:
        total_results = get_detection_count(
            connection,
            minimum_confidence,
        )

        detections = get_detection_rows(
            connection,
            minimum_confidence=minimum_confidence,
            limit=per_page,
            offset=offset,
        )

        stats = get_dashboard_stats(connection)

    total_pages = max(
        1,
        (total_results + per_page - 1) // per_page,
    )

    if page > total_pages and total_results > 0:
        page = total_pages
        offset = (page - 1) * per_page

        with get_database() as connection:
            detections = get_detection_rows(
                connection,
                minimum_confidence=minimum_confidence,
                limit=per_page,
                offset=offset,
            )

    first_result = offset + 1 if total_results else 0
    last_result = min(offset + len(detections), total_results)

    return render_template(
        "activity.html",
        detections=detections,
        stats=stats,
        minimum_confidence=minimum_confidence,
        page=page,
        per_page=per_page,
        total_results=total_results,
        total_pages=total_pages,
        first_result=first_result,
        last_result=last_result,
    )


@app.route("/life-list")
def life_list():
    allowed_sorts = {
        "recent",
        "first",
        "name",
        "detections",
        "confidence",
    }

    sort_by = request.args.get("sort", "recent").strip().lower()

    if sort_by not in allowed_sorts:
        sort_by = "recent"

    with get_database() as connection:
        species = get_life_list_species(
            connection,
            sort_by=sort_by,
        )

        stats = get_dashboard_stats(connection)

        first_species = connection.execute(
            """
            SELECT
                common_name,
                scientific_name,
                MIN(created_at) AS first_detected_at
            FROM detections
            GROUP BY common_name, scientific_name
            ORDER BY first_detected_at ASC
            LIMIT 1
            """
        ).fetchone()

        newest_species = connection.execute(
            """
            SELECT
                common_name,
                scientific_name,
                MIN(created_at) AS first_detected_at
            FROM detections
            GROUP BY common_name, scientific_name
            ORDER BY first_detected_at DESC
            LIMIT 1
            """
        ).fetchone()

        most_detected_species = connection.execute(
            """
            SELECT
                common_name,
                scientific_name,
                COUNT(*) AS total_detections
            FROM detections
            GROUP BY common_name, scientific_name
            ORDER BY
                total_detections DESC,
                common_name COLLATE NOCASE
            LIMIT 1
            """
        ).fetchone()

    return render_template(
        "life_list.html",
        species=species,
        stats=stats,
        sort_by=sort_by,
        first_species=(
            dict(first_species)
            if first_species is not None
            else None
        ),
        newest_species=(
            dict(newest_species)
            if newest_species is not None
            else None
        ),
        most_detected_species=(
            dict(most_detected_species)
            if most_detected_species is not None
            else None
        ),
    )


@app.route("/species/<path:common_name>")
def species_detail(common_name: str):
    try:
        minimum_confidence = float(
            request.args.get("min_confidence", "0")
        )
    except ValueError:
        minimum_confidence = 0.0

    minimum_confidence = max(
        0.0,
        min(minimum_confidence, 1.0),
    )

    with get_database() as connection:
        species_stats = connection.execute(
            """
            SELECT
                common_name,
                scientific_name,
                COUNT(*) AS total_detections,
                ROUND(AVG(confidence) * 100, 1)
                    AS average_confidence,
                ROUND(MAX(confidence) * 100, 1)
                    AS highest_confidence,
                MIN(created_at) AS first_detected_at,
                MAX(created_at) AS last_detected_at,
                COUNT(DISTINCT DATE(created_at))
                    AS active_days
            FROM detections
            WHERE common_name = ?
            GROUP BY common_name, scientific_name
            """,
            (common_name,),
        ).fetchone()

        if species_stats is None:
            abort(404)

        rows = connection.execute(
            """
            SELECT
                d.id AS detection_id,
                d.recording_id,
                d.common_name,
                d.scientific_name,
                d.confidence,
                d.start_time,
                d.end_time,
                d.created_at,
                r.recorded_at,
                r.file_path,
                r.duration_seconds
            FROM detections d
            JOIN recordings r
                ON r.id = d.recording_id
            WHERE d.common_name = ?
              AND d.confidence >= ?
            ORDER BY d.created_at DESC
            LIMIT 250
            """,
            (
                common_name,
                minimum_confidence,
            ),
        ).fetchall()

        detections = []

        for row in rows:
            detection = dict(row)

            recording_path = resolve_recording_path(
                detection["file_path"]
            )

            detection["audio_available"] = bool(
                recording_path
                and recording_path.is_file()
            )

            detections.append(detection)

        daily_activity = connection.execute(
            """
            SELECT
                DATE(created_at) AS activity_date,
                COUNT(*) AS detection_count,
                ROUND(MAX(confidence) * 100, 1)
                    AS highest_confidence
            FROM detections
            WHERE common_name = ?
              AND datetime(created_at) >= datetime(
                  'now',
                  '-14 days'
              )
            GROUP BY DATE(created_at)
            ORDER BY activity_date ASC
            """,
            (common_name,),
        ).fetchall()

    return render_template(
        "species.html",
        species=species_stats,
        detections=detections,
        daily_activity=daily_activity,
        minimum_confidence=minimum_confidence,
    )


@app.route("/audio/<int:recording_id>")
def audio(recording_id: int):
    with get_database() as connection:
        recording = connection.execute(
            """
            SELECT file_path
            FROM recordings
            WHERE id = ?
            """,
            (recording_id,),
        ).fetchone()

    if recording is None:
        abort(404)

    audio_path = resolve_recording_path(
        recording["file_path"]
    )

    if audio_path is None:
        abort(403)

    if not audio_path.is_file():
        abort(404)

    return send_file(
        audio_path,
        mimetype="audio/wav",
        conditional=True,
    )


@app.route("/api/dashboard")
def dashboard_api():
    """Return lightweight live dashboard data for browser refreshes."""
    if not DATABASE_PATH.is_file():
        return jsonify({
            "status": "error",
            "database": "missing",
        }), 500

    with get_database() as connection:
        stats = get_dashboard_stats(connection)
        latest_detection = get_latest_detection(connection)

    latest = dict(latest_detection) if latest_detection is not None else None

    if latest is not None:
        latest_path = resolve_recording_path(latest["file_path"])
        latest["audio_available"] = bool(
            latest_path and latest_path.is_file()
        )
        latest["confidence_percent"] = round(
            float(latest["confidence"]) * 100,
            1,
        )

    return jsonify({
        "status": "ok",
        "stats": stats,
        "latest_detection": latest,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/health")
def health():
    if not DATABASE_PATH.is_file():
        return {
            "status": "error",
            "database": "missing",
        }, 500

    with get_database() as connection:
        latest_recording = connection.execute(
            """
            SELECT MAX(recorded_at) AS recorded_at
            FROM recordings
            """
        ).fetchone()

    latest_recording_at = latest_recording["recorded_at"]
    age_seconds = seconds_since(latest_recording_at)

    recorder_recent = (
        age_seconds is not None
        and age_seconds <= 180
    )

    return {
        "status": "ok",
        "database": "available",
        "hostname": socket.gethostname(),
        "recorder_recent": recorder_recent,
        "latest_recording_at": latest_recording_at,
    }


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8000,
        debug=False,
    )
