import sqlite3
from pathlib import Path

import pytest

from app.migrations import migrate, migration_history


def test_migrations_are_ordered_and_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "station.db"
    applied = migrate(database, tmp_path / "backups")
    expected_versions = [1, 2, 3, 4]
    assert [item.version for item in applied] == expected_versions
    assert migrate(database, tmp_path / "backups") == []
    history = migration_history(database)
    assert [row[0] for row in history] == expected_versions
    assert len({row[0] for row in history}) == len(expected_versions)
    with sqlite3.connect(database) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(stations)")
        }
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert "station_uuid" in columns
    assert {"detections", "verifications", "detection_reviews"} <= tables


def test_failed_migration_rolls_back(tmp_path: Path) -> None:
    directory = tmp_path / "migrations"
    directory.mkdir()
    (directory / "0001_bad.sql").write_text(
        "CREATE TABLE should_rollback (id INTEGER);\nINVALID SQL;\n",
        encoding="utf-8",
    )
    database = tmp_path / "station.db"
    with pytest.raises(sqlite3.Error):
        migrate(database, tmp_path / "backups", directory)
    with sqlite3.connect(database) as connection:
        found = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name='should_rollback'"
        ).fetchone()[0]
    assert found == 0
