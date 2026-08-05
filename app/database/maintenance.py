"""Safe SQLite backup, restore, integrity, and migration operations."""
from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.config import load_config
from app.database.connection import connect_database, initialize_database


def backup_database(source: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / f"fieldmouse-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.db"
    with sqlite3.connect(source) as original, sqlite3.connect(target) as copy:
        original.backup(copy)
    return target


def restore_database(backup: Path, destination: Path) -> None:
    if not backup.is_file():
        raise FileNotFoundError(backup)
    with sqlite3.connect(f"file:{backup}?mode=ro", uri=True) as check:
        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Refusing to restore a corrupt backup")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".restore.tmp")
    shutil.copy2(backup, temporary)
    temporary.replace(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description="Maintain the Field Mouse database")
    parser.add_argument("action", choices=("init", "check", "backup", "restore"))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--file", type=Path, help="Backup file for restore")
    args = parser.parse_args()
    config = load_config(args.config)
    path = config.storage.database_path
    if args.action == "init":
        initialize_database(path)
        print(path)
    elif args.action == "check":
        with connect_database(path) as connection:
            print(connection.execute("PRAGMA integrity_check").fetchone()[0])
    elif args.action == "backup":
        print(backup_database(path, config.storage.backups_directory))
    else:
        if args.file is None:
            parser.error("--file is required for restore")
        restore_database(args.file, path)
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
