import sqlite3
from pathlib import Path
from unittest.mock import patch

from app.config import load_config
from app.database.connection import initialize_database
from app.system.health_check import collect_health


def test_health_report_is_station_scoped(tmp_path: Path) -> None:
    config_file = tmp_path / "config" / "station.toml"
    config_file.parent.mkdir()
    config_file.write_text(
        """
[station]
id = "station-a"
name = "A"
timezone = "UTC"
[storage]
database_path = "data/test.db"
recordings_directory = "data/recordings"
[health]
services = []
""",
        encoding="utf-8",
    )
    config = load_config(config_file, {})
    initialize_database(config.storage.database_path)
    with patch("app.system.health_check.shutil.which", return_value=None):
        result = collect_health(config)
    assert result["station_id"] == "station-a"
    assert result["database"]["integrity"] == "ok"
    assert "disk" in result and "memory" in result
