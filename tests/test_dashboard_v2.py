from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from app.web.v3 import get_wildlife_story


def database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE detections (
            common_name TEXT NOT NULL,
            scientific_name TEXT,
            confidence REAL NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return connection


def station() -> dict:
    return {"timezone": "UTC"}


def test_wildlife_story_has_calm_empty_state() -> None:
    with database() as connection:
        story = get_wildlife_story(connection, station())

    assert story["most_active"] is None
    assert story["new_species_week"] == 0
    assert story["season_detection_count"] == 0
    assert story["season_species_count"] == 0


def test_wildlife_story_prioritizes_todays_most_active_species() -> None:
    now = datetime.now(timezone.utc).isoformat()
    with database() as connection:
        connection.executemany(
            """
            INSERT INTO detections (
                common_name,
                scientific_name,
                confidence,
                created_at
            ) VALUES (?, ?, ?, ?)
            """,
            [
                ("American Robin", "Turdus migratorius", 0.91, now),
                ("American Robin", "Turdus migratorius", 0.96, now),
                ("Song Sparrow", "Melospiza melodia", 0.89, now),
            ],
        )
        story = get_wildlife_story(connection, station())

    assert story["most_active"]["common_name"] == "American Robin"
    assert story["most_active"]["detection_count"] == 2
    assert story["most_active"]["highest_confidence"] == 96.0
    assert story["new_species_week"] == 2
    assert story["season_detection_count"] == 3
    assert story["season_species_count"] == 2
