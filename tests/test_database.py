import sqlite3
from pathlib import Path

import pytest

from app.database.connection import connect_database, initialize_database
from app.database.maintenance import backup_database, restore_database


def test_database_pragmas_and_backup(tmp_path: Path) -> None:
    database = tmp_path / "fieldmouse.db"
    initialize_database(database)
    with connect_database(database) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        connection.execute(
            "INSERT INTO stations VALUES ('one', 'Station', 'UTC', 'now')"
        )
        connection.commit()
    backup = backup_database(database, tmp_path / "backups")
    restored = tmp_path / "restored.db"
    restore_database(backup, restored)
    with sqlite3.connect(restored) as connection:
        assert connection.execute("SELECT COUNT(*) FROM stations").fetchone()[0] == 1


def test_restore_rejects_invalid_database(tmp_path: Path) -> None:
    invalid = tmp_path / "bad.db"
    invalid.write_text("not sqlite", encoding="utf-8")
    with pytest.raises(sqlite3.DatabaseError):
        restore_database(invalid, tmp_path / "target.db")
