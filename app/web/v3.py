"""Read-only presentation helpers for Dashboard V3.

Dashboard V3 is intentionally not activated yet. The live Flask routes can
import these helpers when the final route-switch milestone is approved.
Nothing in this module writes to the station database or controls services.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTENT_ROOT = Path(__file__).resolve().parent / "content"

DEFAULT_STATION = {
    "id": "field-mouse-001",
    "name": "Project Field Mouse",
    "hostname": "field-mouse",
    "timezone": "UTC",
    "dashboard_port": 8000,
}

WEATHER_PLACEHOLDER = {
    "available": False,
    "label": "Weather station coming soon",
    "summary": "Local conditions will appear here in a future update.",
    "asset": "weather/partly-cloudy.png",
}

SEASON_NAMES = {
    12: "Winter",
    1: "Winter",
    2: "Winter",
    3: "Spring",
    4: "Spring",
    5: "Spring",
    6: "Summer",
    7: "Summer",
    8: "Summer",
    9: "Autumn",
    10: "Autumn",
    11: "Autumn",
}


def load_json_content(filename: str, default: Any) -> Any:
    """Load presentation-only content with a safe fallback."""
    try:
        return json.loads(
            (CONTENT_ROOT / filename).read_text(encoding="utf-8")
        )
    except (OSError, ValueError, TypeError):
        return default


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def station_day_bounds(
    timezone_name: str,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Return UTC boundaries for the station's current local date."""
    try:
        station_timezone = ZoneInfo(timezone_name)
    except (KeyError, ValueError):
        station_timezone = timezone.utc

    current = now or datetime.now(timezone.utc)
    local_now = current.astimezone(station_timezone)
    local_start = local_now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    local_end = local_start + timedelta(days=1)

    return (
        local_start.astimezone(timezone.utc),
        local_end.astimezone(timezone.utc),
    )


def season_for_timestamp(value: str | None) -> str:
    parsed = parse_timestamp(value)
    if parsed is None:
        return "Season unknown"

    return SEASON_NAMES[parsed.month]


def build_species_badges(species: dict, newest_name: str | None) -> list[str]:
    badges = []
    detections = int(species.get("total_detections") or 0)
    confidence = float(species.get("highest_confidence") or 0)

    if species.get("common_name") == newest_name:
        badges.append("Recent discovery")

    if detections >= 25:
        badges.append("Frequent visitor")
    elif detections == 1:
        badges.append("First encounter")

    if confidence >= 95:
        badges.append("Clear call")

    return badges[:2]


def enrich_life_list(species_rows: list[dict]) -> list[dict]:
    newest_name = None

    if species_rows:
        newest = max(
            species_rows,
            key=lambda row: row.get("first_detected_at") or "",
        )
        newest_name = newest.get("common_name")

    enriched = []

    for row in species_rows:
        item = dict(row)
        content = get_species_content(item.get("common_name", ""))
        item["season"] = season_for_timestamp(
            item.get("last_detected_at")
        )
        item["badges"] = build_species_badges(item, newest_name)
        item["asset"] = content.get("asset")
        enriched.append(item)

    return enriched


def get_today_summary(connection, station: dict) -> dict:
    start, end = station_day_bounds(station["timezone"])
    row = connection.execute(
        """
        SELECT
            COUNT(*) AS detection_count,
            COUNT(DISTINCT common_name) AS species_count,
            ROUND(AVG(confidence) * 100, 1) AS average_confidence
        FROM detections
        WHERE datetime(created_at) >= datetime(?)
          AND datetime(created_at) < datetime(?)
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchone()

    return {
        "detection_count": row["detection_count"] or 0,
        "species_count": row["species_count"] or 0,
        "average_confidence": row["average_confidence"] or 0,
        "start": start.isoformat(),
        "end": end.isoformat(),
    }


def get_recent_discoveries(connection, limit: int = 4) -> list[dict]:
    rows = connection.execute(
        """
        SELECT
            common_name,
            scientific_name,
            MIN(created_at) AS first_detected_at,
            COUNT(*) AS total_detections
        FROM detections
        GROUP BY common_name, scientific_name
        ORDER BY first_detected_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    return [dict(row) for row in rows]


def get_wildlife_story(connection, station: dict) -> dict:
    """Build compact, read-only narrative highlights for the overview."""
    start, end = station_day_bounds(station["timezone"])
    active = connection.execute(
        """
        SELECT
            common_name,
            scientific_name,
            COUNT(*) AS detection_count,
            ROUND(MAX(confidence) * 100, 1) AS highest_confidence
        FROM detections
        WHERE datetime(created_at) >= datetime(?)
          AND datetime(created_at) < datetime(?)
        GROUP BY common_name, scientific_name
        ORDER BY detection_count DESC, highest_confidence DESC
        LIMIT 1
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchone()
    first_visitor = connection.execute(
        """
        SELECT common_name, scientific_name, created_at
        FROM detections
        WHERE datetime(created_at) >= datetime(?)
          AND datetime(created_at) < datetime(?)
        ORDER BY datetime(created_at) ASC
        LIMIT 1
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchone()
    dawn_end = start + timedelta(hours=9)
    dawn_start = start + timedelta(hours=5)
    dawn = connection.execute(
        """
        SELECT
            COUNT(*) AS detection_count,
            COUNT(DISTINCT common_name) AS species_count
        FROM detections
        WHERE datetime(created_at) >= datetime(?)
          AND datetime(created_at) < datetime(?)
        """,
        (dawn_start.isoformat(), dawn_end.isoformat()),
    ).fetchone()
    new_this_week = connection.execute(
        """
        SELECT COUNT(*) AS species_count
        FROM (
            SELECT common_name
            FROM detections
            GROUP BY common_name
            HAVING datetime(MIN(created_at)) >= datetime('now', '-7 days')
        )
        """
    ).fetchone()
    season = SEASON_NAMES[datetime.now(timezone.utc).month]
    seasonal = connection.execute(
        """
        SELECT
            COUNT(*) AS detection_count,
            COUNT(DISTINCT common_name) AS species_count
        FROM detections
        WHERE datetime(created_at) >= datetime('now', '-30 days')
        """
    ).fetchone()
    return_visit = connection.execute(
        """
        WITH visits AS (
            SELECT
                common_name,
                scientific_name,
                created_at,
                LAG(created_at) OVER (
                    PARTITION BY common_name
                    ORDER BY datetime(created_at)
                ) AS previous_at
            FROM detections
        )
        SELECT
            common_name,
            scientific_name,
            created_at,
            previous_at,
            CAST(
                julianday(created_at) - julianday(previous_at)
                AS INTEGER
            ) AS absence_days
        FROM visits
        WHERE previous_at IS NOT NULL
          AND datetime(created_at) >= datetime('now', '-7 days')
          AND julianday(created_at) - julianday(previous_at) >= 1
        ORDER BY absence_days DESC, datetime(created_at) DESC
        LIMIT 1
        """
    ).fetchone()

    return {
        "most_active": dict(active) if active is not None else None,
        "first_visitor": (
            dict(first_visitor) if first_visitor is not None else None
        ),
        "dawn_detection_count": dawn["detection_count"] or 0,
        "dawn_species_count": dawn["species_count"] or 0,
        "return_visit": (
            dict(return_visit) if return_visit is not None else None
        ),
        "new_species_week": new_this_week["species_count"] or 0,
        "season": season,
        "season_detection_count": seasonal["detection_count"] or 0,
        "season_species_count": seasonal["species_count"] or 0,
    }


def get_weekly_activity(connection, station: dict) -> list[dict]:
    """Return seven station-local day buckets, including quiet days."""
    today_start, today_end = station_day_bounds(station["timezone"])
    week_start = today_start - timedelta(days=6)
    rows = connection.execute(
        """
        SELECT
            DATE(created_at) AS activity_date,
            COUNT(*) AS detection_count,
            COUNT(DISTINCT common_name) AS species_count
        FROM detections
        WHERE datetime(created_at) >= datetime(?)
          AND datetime(created_at) < datetime(?)
        GROUP BY DATE(created_at)
        """,
        (week_start.isoformat(), today_end.isoformat()),
    ).fetchall()
    counts = {row["activity_date"]: dict(row) for row in rows}

    activity = []
    for offset in range(7):
        day = (week_start + timedelta(days=offset)).date()
        key = day.isoformat()
        values = counts.get(key, {})
        activity.append({
            "activity_date": key,
            "label": day.strftime("%a"),
            "detection_count": values.get("detection_count", 0),
            "species_count": values.get("species_count", 0),
        })

    return activity


def get_species_observation_profile(
    connection,
    common_name: str,
) -> dict:
    """Summarize when a species tends to visit without changing APIs."""
    busiest = connection.execute(
        """
        SELECT
            CAST(strftime('%H', created_at) AS INTEGER) AS hour,
            COUNT(*) AS detection_count
        FROM detections
        WHERE common_name = ?
        GROUP BY strftime('%H', created_at)
        ORDER BY detection_count DESC, hour ASC
        LIMIT 1
        """,
        (common_name,),
    ).fetchone()
    recent = connection.execute(
        """
        SELECT
            COUNT(*) AS detection_count,
            COUNT(DISTINCT DATE(created_at)) AS active_days,
            ROUND(AVG(confidence) * 100, 1) AS average_confidence
        FROM detections
        WHERE common_name = ?
          AND datetime(created_at) >= datetime('now', '-30 days')
        """,
        (common_name,),
    ).fetchone()

    hour = int(busiest["hour"]) if busiest is not None else None
    if hour is None:
        hour_label = "Still learning"
    else:
        hour_label = f"{hour % 12 or 12} {'AM' if hour < 12 else 'PM'}"

    return {
        "typical_hour": hour,
        "typical_hour_label": hour_label,
        "typical_hour_count": (
            busiest["detection_count"] if busiest is not None else 0
        ),
        "recent_detection_count": recent["detection_count"] or 0,
        "recent_active_days": recent["active_days"] or 0,
        "recent_average_confidence": recent["average_confidence"] or 0,
    }


def get_activity_timeline(connection, station: dict) -> list[dict]:
    start, end = station_day_bounds(station["timezone"])
    rows = connection.execute(
        """
        SELECT
            CAST(strftime('%H', created_at) AS INTEGER) AS hour,
            COUNT(*) AS detection_count
        FROM detections
        WHERE datetime(created_at) >= datetime(?)
          AND datetime(created_at) < datetime(?)
        GROUP BY strftime('%H', created_at)
        ORDER BY hour
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    counts = {int(row["hour"]): row["detection_count"] for row in rows}

    timeline = []

    for hour in range(24):
        hour_12 = hour % 12 or 12
        suffix = "AM" if hour < 12 else "PM"
        timeline.append({
            "hour": hour,
            "label": f"{hour_12} {suffix}",
            "detection_count": counts.get(hour, 0),
        })

    return timeline


def get_species_streak(connection, station: dict) -> dict:
    rows = connection.execute(
        """
        SELECT DISTINCT DATE(created_at) AS activity_date
        FROM detections
        ORDER BY activity_date DESC
        """
    ).fetchall()
    observed_dates = {
        datetime.fromisoformat(row["activity_date"]).date()
        for row in rows
        if row["activity_date"]
    }

    try:
        station_timezone = ZoneInfo(station["timezone"])
    except (KeyError, ValueError):
        station_timezone = timezone.utc

    cursor = datetime.now(timezone.utc).astimezone(station_timezone).date()

    if cursor not in observed_dates:
        cursor -= timedelta(days=1)

    streak = 0
    while cursor in observed_dates:
        streak += 1
        cursor -= timedelta(days=1)

    return {
        "days": streak,
        "active": streak > 0,
    }


def get_recent_recordings(
    connection,
    resolve_path: Callable[[str], Path | None] | None = None,
    limit: int = 5,
) -> list[dict]:
    rows = connection.execute(
        """
        SELECT
            r.id AS recording_id,
            r.recorded_at,
            r.duration_seconds,
            r.file_size_bytes,
            r.file_path,
            COUNT(d.id) AS detection_count
        FROM recordings r
        LEFT JOIN detections d ON d.recording_id = r.id
        GROUP BY r.id
        ORDER BY r.recorded_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    recordings = []

    for row in rows:
        item = dict(row)
        recording_path = (
            resolve_path(item["file_path"])
            if resolve_path is not None
            else None
        )
        item["audio_available"] = bool(
            recording_path and recording_path.is_file()
        )
        recordings.append(item)

    return recordings


def get_confidence_distribution(
    detections: list[dict],
) -> list[dict]:
    buckets = [
        {"label": "60–69%", "minimum": 0.6, "maximum": 0.7, "count": 0},
        {"label": "70–79%", "minimum": 0.7, "maximum": 0.8, "count": 0},
        {"label": "80–89%", "minimum": 0.8, "maximum": 0.9, "count": 0},
        {"label": "90–100%", "minimum": 0.9, "maximum": 1.01, "count": 0},
    ]

    for detection in detections:
        confidence = float(detection.get("confidence") or 0)
        for bucket in buckets:
            if bucket["minimum"] <= confidence < bucket["maximum"]:
                bucket["count"] += 1
                break

    maximum = max((bucket["count"] for bucket in buckets), default=0)
    for bucket in buckets:
        bucket["percent"] = (
            round((bucket["count"] / maximum) * 100, 1)
            if maximum
            else 0
        )

    return buckets


def get_species_content(common_name: str) -> dict:
    registry = load_json_content("species.json", {})
    fallback = registry.get("_default", {})
    return {
        **fallback,
        **registry.get(common_name, {}),
    }


def get_nature_tip(now: datetime | None = None) -> dict:
    tips = load_json_content("nature_tips.json", [])

    if not tips:
        return {
            "title": "Listen before looking",
            "text": (
                "Pause for one quiet minute outside. Wildlife often "
                "announces itself before it comes into view."
            ),
        }

    current = now or datetime.now(timezone.utc)
    return tips[current.toordinal() % len(tips)]


def build_overview_context(
    connection,
    *,
    stats: dict,
    latest_visitors: list[dict],
    resolve_path: Callable[[str], Path | None] | None = None,
    station: dict | None = None,
) -> dict:
    selected_station = {**DEFAULT_STATION, **(station or {})}

    return {
        "station": selected_station,
        "stats": stats,
        "today": get_today_summary(connection, selected_station),
        "wildlife_story": get_wildlife_story(connection, selected_station),
        "weekly_activity": get_weekly_activity(connection, selected_station),
        "latest_visitors": latest_visitors,
        "recent_discoveries": get_recent_discoveries(connection),
        "species_streak": get_species_streak(
            connection,
            selected_station,
        ),
        "activity_timeline": get_activity_timeline(
            connection,
            selected_station,
        ),
        "recent_recordings": get_recent_recordings(
            connection,
            resolve_path=resolve_path,
        ),
        "weather": WEATHER_PLACEHOLDER,
        "nature_tip": get_nature_tip(),
    }
