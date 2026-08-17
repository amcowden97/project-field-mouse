from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file

from app.config import load_config
from app.metrics import metrics_snapshot
from app.system.health_check import collect_health
from app.web.v3 import (
    build_overview_context,
    enrich_life_list,
    get_confidence_distribution,
    get_species_observation_profile,
    get_species_content,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG = load_config()
DATABASE_PATH = CONFIG.storage.database_path
RECORDINGS_ROOT = CONFIG.storage.recordings_directory.resolve()

app = Flask(__name__)


def dashboard_station() -> dict:
    """Expose centralized station configuration to presentation templates."""
    return {
        "id": CONFIG.station.id,
        "name": CONFIG.station.name,
        "hostname": socket.gethostname(),
        "timezone": CONFIG.station.timezone,
        "dashboard_port": CONFIG.dashboard.port,
    }


def get_database() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def resolve_recording_path(file_path: str) -> Path | None:
    path = (PROJECT_ROOT / file_path).resolve()

    if path != RECORDINGS_ROOT and RECORDINGS_ROOT not in path.parents:
        return None

    return path


def display_storage_path(
    path: Path,
    project_root: Path = PROJECT_ROOT,
) -> str:
    """Display project paths relatively and deployed state paths absolutely."""
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


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


def run_system_command(
    command: list[str],
    timeout: float = 3.0,
) -> str | None:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (
        FileNotFoundError,
        subprocess.SubprocessError,
    ):
        return None

    output = result.stdout.strip()

    if not output:
        output = result.stderr.strip()

    return output or None


def get_service_information(service_name: str) -> dict:
    active_state = run_system_command(
        [
            "systemctl",
            "is-active",
            service_name,
        ]
    )

    enabled_state = run_system_command(
        [
            "systemctl",
            "is-enabled",
            service_name,
        ]
    )

    active = active_state == "active"

    if active:
        display_state = "Running"
        state_class = "healthy"
    elif active_state in {"activating", "reloading"}:
        display_state = "Starting"
        state_class = "warning"
    elif active_state in {
        "inactive",
        "failed",
        "deactivating",
    }:
        display_state = (
            active_state.capitalize()
            if active_state
            else "Unavailable"
        )
        state_class = "offline"
    else:
        display_state = active_state or "Unavailable"
        state_class = "unknown"

    return {
        "name": service_name,
        "active": active,
        "active_state": active_state or "unknown",
        "enabled_state": enabled_state or "unknown",
        "display_state": display_state,
        "state_class": state_class,
    }


def get_cpu_temperature() -> float | None:
    thermal_path = Path(
        "/sys/class/thermal/thermal_zone0/temp"
    )

    try:
        raw_value = thermal_path.read_text().strip()
        return round(float(raw_value) / 1000, 1)
    except (
        OSError,
        ValueError,
    ):
        return None


def get_system_uptime_seconds() -> float | None:
    try:
        return float(
            Path("/proc/uptime")
            .read_text()
            .split()[0]
        )
    except (
        OSError,
        ValueError,
        IndexError,
    ):
        return None


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "Unavailable"

    total_minutes = int(seconds // 60)
    days, remaining_minutes = divmod(
        total_minutes,
        24 * 60,
    )
    hours, minutes = divmod(
        remaining_minutes,
        60,
    )

    parts = []

    if days:
        parts.append(
            f"{days} day" if days == 1 else f"{days} days"
        )

    if hours:
        parts.append(
            f"{hours} hour" if hours == 1 else f"{hours} hours"
        )

    if minutes or not parts:
        parts.append(
            f"{minutes} minute"
            if minutes == 1
            else f"{minutes} minutes"
        )

    return ", ".join(parts[:2])


def get_primary_ip_address() -> str | None:
    route_output = run_system_command(
        [
            "hostname",
            "-I",
        ]
    )

    if not route_output:
        return None

    addresses = [
        address
        for address in route_output.split()
        if not address.startswith("127.")
    ]

    return addresses[0] if addresses else None


def get_load_average() -> dict:
    try:
        one, five, fifteen = os.getloadavg()
    except (AttributeError, OSError):
        return {
            "one": None,
            "five": None,
            "fifteen": None,
        }

    return {
        "one": round(one, 2),
        "five": round(five, 2),
        "fifteen": round(fifteen, 2),
    }


def get_memory_information() -> dict:
    values = {}

    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            values[key] = int(value.strip().split()[0]) * 1024
    except (
        OSError,
        ValueError,
        IndexError,
    ):
        return {
            "total": None,
            "available": None,
            "used": None,
            "percent": None,
        }

    total = values.get("MemTotal")
    available = values.get("MemAvailable")

    if not total or available is None:
        return {
            "total": total,
            "available": available,
            "used": None,
            "percent": None,
        }

    used = total - available

    return {
        "total": total,
        "available": available,
        "used": used,
        "percent": round((used / total) * 100, 1),
    }


def get_device_information() -> dict:
    services = [
        get_service_information(
            "fieldmouse-recorder.service"
        ),
        get_service_information(
            "fieldmouse-birdnet.service"
        ),
        get_service_information(
            "fieldmouse-dashboard.service"
        ),
        get_service_information(
            "fieldmouse-storage-manager.timer"
        ),
    ]

    service_labels = {
        "fieldmouse-recorder.service": "Audio recorder",
        "fieldmouse-birdnet.service": "BirdNET detector",
        "fieldmouse-dashboard.service": "Web dashboard",
        "fieldmouse-storage-manager.timer": "Storage cleanup",
    }

    for service in services:
        service["label"] = service_labels.get(
            service["name"],
            service["name"],
        )

    return {
        "hostname": socket.gethostname(),
        "ip_address": get_primary_ip_address(),
        "cpu_temperature": get_cpu_temperature(),
        "uptime_seconds": get_system_uptime_seconds(),
        "uptime": format_duration(
            get_system_uptime_seconds()
        ),
        "load_average": get_load_average(),
        "memory": get_memory_information(),
        "services": services,
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "process_uptime": format_duration(
            time.monotonic()
        ),
    }


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
            r.duration_seconds,
            v.consensus_score AS verification_score,
            v.status AS verification_status,
            v.reason AS verification_reason,
            v.evidence_json AS verification_evidence_json
        FROM detections d
        JOIN recordings r ON r.id = d.recording_id
        LEFT JOIN verifications v ON v.detection_id = d.id
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
        detection["verification"] = build_verification_presentation(
            detection
        )

        detections.append(detection)

    return detections


def build_verification_presentation(row: dict) -> dict | None:
    """Normalize persisted Verification V2 evidence for Dashboard V2."""
    status = row.get("verification_status")
    if not status:
        return None

    try:
        stored_evidence = json.loads(
            row.get("verification_evidence_json") or "[]"
        )
    except (TypeError, ValueError):
        stored_evidence = []

    evidence = []
    for item in stored_evidence if isinstance(stored_evidence, list) else []:
        if not isinstance(item, dict):
            continue
        evidence.append({
            "source": item.get("source", "Evidence source"),
            "verdict": item.get("outcome", "neutral"),
            "reason": item.get("summary", "No explanation supplied."),
        })

    return {
        "status": status,
        "score": row.get("verification_score") or 0.0,
        "explanation": row.get("verification_reason"),
        "evidence": evidence,
    }


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

        context = build_overview_context(
            connection,
            stats=stats,
            latest_visitors=detections,
            resolve_path=resolve_recording_path,
            station=dashboard_station(),
        )

    return render_template(
        "v3/overview.html",
        **context,
        detections=detections,
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
        "v3/activity.html",
        station=dashboard_station(),
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
        species = enrich_life_list(
            get_life_list_species(connection, sort_by=sort_by)
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
        "v3/life_list.html",
        station=dashboard_station(),
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
        observation_profile = get_species_observation_profile(
            connection,
            common_name,
        )
        observed_species_names = {
            row["common_name"]
            for row in connection.execute(
                "SELECT DISTINCT common_name FROM detections"
            ).fetchall()
        }

    return render_template(
        "v3/species.html",
        station=dashboard_station(),
        species=species_stats,
        detections=detections,
        daily_activity=daily_activity,
        observation_profile=observation_profile,
        observed_species_names=observed_species_names,
        species_content=get_species_content(common_name),
        confidence_distribution=get_confidence_distribution(detections),
        minimum_confidence=minimum_confidence,
    )


@app.route("/device")
def device():
    with get_database() as connection:
        stats = get_dashboard_stats(connection)

        database_stats = connection.execute(
            """
            SELECT
                (
                    SELECT COUNT(*)
                    FROM recordings
                ) AS recording_count,
                (
                    SELECT COUNT(*)
                    FROM detections
                ) AS detection_count,
                (
                    SELECT MAX(recorded_at)
                    FROM recordings
                ) AS latest_recording_at,
                (
                    SELECT MAX(created_at)
                    FROM detections
                ) AS latest_detection_at
            """
        ).fetchone()

    database_size = (
        DATABASE_PATH.stat().st_size
        if DATABASE_PATH.is_file()
        else 0
    )

    device_info = get_device_information()

    return render_template(
        "v3/device.html",
        station=dashboard_station(),
        stats=stats,
        device=device_info,
        database_stats=dict(database_stats),
        database_size=database_size,
        database_path=display_storage_path(DATABASE_PATH),
        recordings_path=display_storage_path(RECORDINGS_ROOT),
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


@app.route("/api/metrics")
def metrics_api():
    if not DATABASE_PATH.is_file():
        return jsonify({"status": "error", "database": "missing"}), 503
    with get_database() as connection:
        snapshot = metrics_snapshot(connection)
    return jsonify({
        "status": "ok",
        "station_id": CONFIG.station.id,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "metrics": snapshot,
    })


@app.route("/health")
def health():
    result = collect_health(CONFIG)
    return jsonify(result), (200 if result["status"] == "ok" else 503)


if __name__ == "__main__":
    app.run(
        host=CONFIG.dashboard.host,
        port=CONFIG.dashboard.port,
        debug=False,
    )
