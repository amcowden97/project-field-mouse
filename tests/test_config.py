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


def test_legacy_birdnet_poll_interval_is_migrated(tmp_path: Path) -> None:
    config_file = tmp_path / "station.toml"
    config_file.write_text(
        '[station]\nid="x"\nname="X"\ntimezone="UTC"\n'
        "[birdnet]\npoll_interval=17\n",
        encoding="utf-8",
    )

    config = load_config(config_file, {})

    assert config.birdnet.poll_interval_seconds == 17


def test_legacy_birdnet_environment_override_is_migrated(
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "station.toml"
    write_config(config_file)

    config = load_config(config_file, {"PFM_BIRDNET_POLL_INTERVAL": "23"})

    assert config.birdnet.poll_interval_seconds == 23


def test_conflicting_birdnet_poll_intervals_are_rejected(
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "station.toml"
    config_file.write_text(
        '[station]\nid="x"\nname="X"\ntimezone="UTC"\n'
        "[birdnet]\npoll_interval=17\npoll_interval_seconds=10\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="Conflicting configuration"):
        load_config(config_file, {})


def test_invalid_timezone_is_rejected(tmp_path: Path) -> None:
    config_file = tmp_path / "station.toml"
    config_file.write_text(
        '[station]\nid="x"\nname="X"\ntimezone="Mars/Olympus"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError):
        load_config(config_file, {})


def test_legacy_disk_warning_is_migrated_to_graduated_watermarks(tmp_path: Path) -> None:
    config_file = tmp_path / "station.toml"
    config_file.write_text(
        '[station]\nid="x"\nname="X"\ntimezone="UTC"\n'
        "[health]\ndisk_warning_percent=85.0\n",
        encoding="utf-8",
    )
    config = load_config(config_file, {})
    assert (
        config.health.disk_advisory_percent,
        config.health.disk_warning_percent,
        config.health.disk_critical_percent,
        config.health.disk_emergency_percent,
    ) == (80.0, 90.0, 95.0, 98.0)
