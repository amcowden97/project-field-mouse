from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path("config/station.toml")


class ConfigurationError(RuntimeError):
    """Raised when the Field Mouse configuration is invalid."""


@dataclass(frozen=True)
class StationConfig:
    id: str
    name: str
    timezone: str


@dataclass(frozen=True)
class AudioConfig:
    device: str
    sample_rate: int
    channels: int
    sample_format: str
    recording_duration_seconds: int
    recording_interval_seconds: int


@dataclass(frozen=True)
class StorageConfig:
    recordings_directory: Path
    database_path: Path
    logs_directory: Path


@dataclass(frozen=True)
class DetectionConfig:
    enabled: bool
    minimum_confidence: float


@dataclass(frozen=True)
class FieldMouseConfig:
    station: StationConfig
    audio: AudioConfig
    storage: StorageConfig
    detection: DetectionConfig


def require_section(
    config_data: dict[str, Any],
    section_name: str,
) -> dict[str, Any]:
    section = config_data.get(section_name)

    if not isinstance(section, dict):
        raise ConfigurationError(
            f"Missing or invalid configuration section: [{section_name}]"
        )

    return section


def require_string(
    section: dict[str, Any],
    key: str,
    section_name: str,
) -> str:
    value = section.get(key)

    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(
            f"[{section_name}].{key} must be a non-empty string."
        )

    return value.strip()


def require_integer(
    section: dict[str, Any],
    key: str,
    section_name: str,
    minimum: int = 1,
) -> int:
    value = section.get(key)

    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigurationError(
            f"[{section_name}].{key} must be an integer."
        )

    if value < minimum:
        raise ConfigurationError(
            f"[{section_name}].{key} must be at least {minimum}."
        )

    return value


def require_boolean(
    section: dict[str, Any],
    key: str,
    section_name: str,
) -> bool:
    value = section.get(key)

    if not isinstance(value, bool):
        raise ConfigurationError(
            f"[{section_name}].{key} must be true or false."
        )

    return value


def require_float(
    section: dict[str, Any],
    key: str,
    section_name: str,
    minimum: float,
    maximum: float,
) -> float:
    value = section.get(key)

    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigurationError(
            f"[{section_name}].{key} must be a number."
        )

    numeric_value = float(value)

    if not minimum <= numeric_value <= maximum:
        raise ConfigurationError(
            f"[{section_name}].{key} must be between "
            f"{minimum} and {maximum}."
        )

    return numeric_value


def load_config(
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> FieldMouseConfig:
    if not config_path.exists():
        raise ConfigurationError(
            f"Configuration file not found: {config_path}"
        )

    try:
        with config_path.open("rb") as config_file:
            config_data = tomllib.load(config_file)
    except tomllib.TOMLDecodeError as error:
        raise ConfigurationError(
            f"Invalid TOML in {config_path}: {error}"
        ) from error
    except OSError as error:
        raise ConfigurationError(
            f"Could not read configuration file: {error}"
        ) from error

    station = require_section(config_data, "station")
    audio = require_section(config_data, "audio")
    storage = require_section(config_data, "storage")
    detection = require_section(config_data, "detection")

    return FieldMouseConfig(
        station=StationConfig(
            id=require_string(station, "id", "station"),
            name=require_string(station, "name", "station"),
            timezone=require_string(station, "timezone", "station"),
        ),
        audio=AudioConfig(
            device=require_string(audio, "device", "audio"),
            sample_rate=require_integer(
                audio,
                "sample_rate",
                "audio",
            ),
            channels=require_integer(
                audio,
                "channels",
                "audio",
            ),
            sample_format=require_string(
                audio,
                "sample_format",
                "audio",
            ),
            recording_duration_seconds=require_integer(
                audio,
                "recording_duration_seconds",
                "audio",
            ),
            recording_interval_seconds=require_integer(
                audio,
                "recording_interval_seconds",
                "audio",
            ),
        ),
        storage=StorageConfig(
            recordings_directory=Path(
                require_string(
                    storage,
                    "recordings_directory",
                    "storage",
                )
            ),
            database_path=Path(
                require_string(
                    storage,
                    "database_path",
                    "storage",
                )
            ),
            logs_directory=Path(
                require_string(
                    storage,
                    "logs_directory",
                    "storage",
                )
            ),
        ),
        detection=DetectionConfig(
            enabled=require_boolean(
                detection,
                "enabled",
                "detection",
            ),
            minimum_confidence=require_float(
                detection,
                "minimum_confidence",
                "detection",
                minimum=0.0,
                maximum=1.0,
            ),
        ),
    )
