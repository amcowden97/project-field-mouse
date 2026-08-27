import sqlite3
from pathlib import Path

import pytest

from app.migrations import discover_migrations, migrate, migration_history


def test_migrations_are_ordered_and_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "station.db"
    applied = migrate(database, tmp_path / "backups")
    expected_versions = [1, 2, 3, 4, 5, 6]
    assert [item.version for item in applied] == expected_versions
    assert migrate(database, tmp_path / "backups") == []
    history = migration_history(database)
    assert [row[0] for row in history] == expected_versions
    assert len({row[0] for row in history}) == len(expected_versions)
    with sqlite3.connect(database) as connection:
        station_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(stations)")
        }
        recording_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(recordings)")
        }
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
    assert "station_uuid" in station_columns
    assert {
        "recording_identity",
        "source_availability",
        "media_type",
        "source_sha256",
    } <= recording_columns
    assert {
        "detections",
        "verifications",
        "detection_reviews",
        "recording_source_events",
        "evidence",
        "evidence_sources",
        "recording_protections",
    } <= tables
    assert {
        "idx_detections_created",
        "idx_detections_datetime_created",
    } <= indexes


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


def test_migration_checksum_is_stable_across_line_endings(tmp_path: Path) -> None:
    lf_directory = tmp_path / "lf"
    crlf_directory = tmp_path / "crlf"
    lf_directory.mkdir()
    crlf_directory.mkdir()
    sql = "CREATE TABLE example (id INTEGER);\nINSERT INTO example VALUES (1);\n"
    (lf_directory / "0001_example.sql").write_bytes(sql.encode("utf-8"))
    (crlf_directory / "0001_example.sql").write_bytes(
        sql.replace("\n", "\r\n").encode("utf-8")
    )

    assert discover_migrations(lf_directory)[0].checksum == discover_migrations(
        crlf_directory
    )[0].checksum
