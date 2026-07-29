"""Portable, compressed station backups with cryptographic verification."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import FieldMouseConfig
from app.database.maintenance import backup_database


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(config: FieldMouseConfig, config_path: Path) -> Path:
    config.storage.backups_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = config.storage.backups_directory / f"fieldmouse-{config.station.id}-{timestamp}.zip"
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        database = backup_database(config.storage.database_path, root)
        station = root / "station.toml"
        station.write_bytes(config_path.read_bytes())
        metadata = {
            "format": 1, "station_id": config.station.id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "files": {
                "database.db": _sha256(database),
                "station.toml": _sha256(station),
            },
        }
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
            output.write(database, "database.db")
            output.write(station, "station.toml")
            output.writestr("manifest.json", json.dumps(metadata, indent=2))
    verify_backup(archive)
    prune_backups(
        config.storage.backups_directory,
        config.storage.backup_retention_days,
        config.storage.maximum_backups,
        preserve=archive,
    )
    return archive


def prune_backups(
    directory: Path,
    retention_days: int,
    maximum_backups: int,
    preserve: Path | None = None,
) -> list[Path]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    archives = sorted(directory.glob("fieldmouse-*.zip"), key=lambda item: item.stat().st_mtime,
                      reverse=True)
    removed = []
    for index, archive in enumerate(archives):
        modified = datetime.fromtimestamp(archive.stat().st_mtime, timezone.utc)
        if archive != preserve and (index >= maximum_backups or modified < cutoff):
            archive.unlink()
            removed.append(archive)
    return removed


def verify_backup(archive: Path) -> dict:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(archive) as source:
            allowed = {"database.db", "station.toml", "manifest.json"}
            if set(source.namelist()) != allowed:
                raise RuntimeError("Backup contains unexpected or missing files")
            source.extractall(root)
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        for name, expected in manifest["files"].items():
            if _sha256(root / name) != expected:
                raise RuntimeError(f"Backup checksum failed for {name}")
        with sqlite3.connect(f"file:{root / 'database.db'}?mode=ro", uri=True) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(f"Backup database is corrupt: {integrity}")
    return manifest


def restore_backup(
    archive: Path,
    database_path: Path,
    config_destination: Path | None = None,
) -> None:
    verify_backup(archive)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(archive) as source:
            source.extract("database.db", root)
            source.extract("station.toml", root)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_database = database_path.with_suffix(".restore.tmp")
        temporary_database.write_bytes((root / "database.db").read_bytes())
        temporary_database.replace(database_path)
        if config_destination:
            config_destination.parent.mkdir(parents=True, exist_ok=True)
            config_destination.write_bytes((root / "station.toml").read_bytes())
