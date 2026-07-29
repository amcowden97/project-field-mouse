from pathlib import Path

from app.backups import create_backup, restore_backup, verify_backup
from app.config import load_config
from app.migrations import migrate


def test_archive_backup_round_trip(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "station.toml"
    config_path.parent.mkdir()
    config_path.write_text(
        """
[station]
id = "backup-test"
name = "Backup Test"
timezone = "UTC"
[storage]
database_path = "data/station.db"
backups_directory = "backups"
""",
        encoding="utf-8",
    )
    config = load_config(config_path, {})
    migrate(config.storage.database_path, config.storage.backups_directory)
    archive = create_backup(config, config_path)
    assert verify_backup(archive)["station_id"] == "backup-test"
    restored = tmp_path / "restored.db"
    restore_backup(archive, restored)
    assert restored.is_file()
