from pathlib import Path

import pytest

from app.config import ConfigurationError, load_config


def write_config(path: Path) -> None:
    path.write_text(
        """
[station]
id = "test-001"
name = "Test Station"
timezone = "UTC"
[storage]
database_path = "var/test.db"
""",
        encoding="utf-8",
    )


def test_defaults_and_relative_paths(tmp_path: Path) -> None:
    config_file = tmp_path / "config" / "station.toml"
    config_file.parent.mkdir()
    write_config(config_file)
    config = load_config(config_file, {})
    assert config.station.id == "test-001"
    assert config.audio.sample_rate == 48000
    assert config.storage.database_path == tmp_path / "var" / "test.db"


def test_environment_override(tmp_path: Path) -> None:
    config_file = tmp_path / "config" / "station.toml"
    config_file.parent.mkdir()
    write_config(config_file)
    config = load_config(
        config_file,
        {"PFM_DASHBOARD_PORT": "9000", "PFM_DETECTION_ENABLED": "false"},
    )
    assert config.dashboard.port == 9000
    assert config.detection.enabled is False


def test_invalid_timezone_is_rejected(tmp_path: Path) -> None:
    config_file = tmp_path / "station.toml"
    config_file.write_text(
        '[station]\nid="x"\nname="X"\ntimezone="Mars/Olympus"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError):
        load_config(config_file, {})
