"""Central, validated configuration for every Field Mouse service."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "station.toml"


class ConfigurationError(RuntimeError):
    """Raised when station configuration is invalid."""


@dataclass(frozen=True)
class StationConfig:
    id: str = "field-mouse-001"
    uuid: str = ""
    name: str = "Project Field Mouse"
    timezone: str = "UTC"
    latitude: float | None = None
    longitude: float | None = None
    location_name: str = ""
    hardware_version: str = "unknown"
    deployment_date: str = ""
    capabilities: tuple[str, ...] = ("audio", "birdnet")


@dataclass(frozen=True)
class AudioConfig:
    device: str = "default"
    sample_rate: int = 48_000
    channels: int = 1
    sample_format: str = "S16_LE"
    recording_duration_seconds: int = 60
    recording_interval_seconds: int = 900


@dataclass(frozen=True)
class StorageConfig:
    recordings_directory: Path = PROJECT_ROOT / "data" / "recordings"
    database_path: Path = PROJECT_ROOT / "data" / "database" / "fieldmouse.db"
    logs_directory: Path = PROJECT_ROOT / "logs"
    backups_directory: Path = PROJECT_ROOT / "data" / "backups"
    empty_recording_retention_days: int = 1
    detection_recording_retention_days: int = 3
    rare_species: tuple[str, ...] = ()
    cleanup_interval_hours: int = 6
    minimum_free_gb: float = 2.0
    maximum_disk_percent: float = 90.0
    backup_retention_days: int = 30
    maximum_backups: int = 20


@dataclass(frozen=True)
class DetectionConfig:
    enabled: bool = True
    minimum_confidence: float = 0.70
    species_include: tuple[str, ...] = ()
    species_exclude: tuple[str, ...] = ()


@dataclass(frozen=True)
class BirdNETConfig:
    enabled: bool = True
    latitude: float | None = None
    longitude: float | None = None
    minimum_confidence: float = 0.25
    occurrence_threshold: float = 0.03
    poll_interval_seconds: int = 10


@dataclass(frozen=True)
class DashboardConfig:
    host: str = "0.0.0.0"
    port: int = 8000


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    max_bytes: int = 5_000_000
    backup_count: int = 5
    json: bool = True


@dataclass(frozen=True)
class HealthConfig:
    recording_stale_seconds: int = 1200
    birdnet_stale_seconds: int = 1800
    cleanup_stale_seconds: int = 28800
    disk_advisory_percent: float = 80.0
    disk_warning_percent: float = 90.0
    disk_critical_percent: float = 95.0
    disk_emergency_percent: float = 98.0
    temperature_warning_c: float = 75.0
    notification_webhook_url: str = ""
    notification_timeout_seconds: int = 5
    services: tuple[str, ...] = (
        "fieldmouse-recorder.service",
        "fieldmouse-birdnet.service",
        "fieldmouse-dashboard.service",
    )


@dataclass(frozen=True)
class FieldMouseConfig:
    station: StationConfig
    audio: AudioConfig
    storage: StorageConfig
    detection: DetectionConfig
    birdnet: BirdNETConfig
    dashboard: DashboardConfig
    logging: LoggingConfig
    health: HealthConfig


DEFAULTS: dict[str, dict[str, Any]] = {
    "station": {}, "audio": {}, "storage": {}, "detection": {},
    "birdnet": {}, "dashboard": {}, "logging": {}, "health": {},
}

CONFIG_ALIASES: dict[str, dict[str, str]] = {
    # Production configurations created before the shared RC1 configuration
    # schema used this shorter name.
    "birdnet": {"poll_interval": "poll_interval_seconds"},
}


def _merge(base: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    merged = {key: dict(value) for key, value in base.items()}
    for section, section_values in values.items():
        if section in merged and isinstance(section_values, dict):
            merged[section].update(section_values)
    return merged


def _migrate_compatibility_fields(data: dict[str, dict[str, Any]]) -> None:
    """Translate supported legacy fields without hiding ambiguous values."""
    for section, aliases in CONFIG_ALIASES.items():
        values = data[section]
        for legacy, current in aliases.items():
            if legacy not in values:
                continue
            if current in values and values[current] != values[legacy]:
                raise ConfigurationError(
                    f"Conflicting configuration fields: {section}.{legacy} "
                    f"and {section}.{current}"
                )
            values[current] = values.pop(legacy)
    health = data["health"]
    new_watermarks = {
        "disk_advisory_percent",
        "disk_critical_percent",
        "disk_emergency_percent",
    }
    if (
        health.get("disk_warning_percent") == 85.0
        and not new_watermarks.intersection(health)
    ):
        # RC1 used one 85% blocking threshold. RC1.1.1 replaces it with the
        # documented 80/90/95/98 graduated policy.
        health.pop("disk_warning_percent")


def _environment(data: dict[str, Any], environ: dict[str, str]) -> None:
    """Apply PFM_SECTION_KEY overrides, inferring the target value's type."""
    for name, raw in environ.items():
        if not name.startswith("PFM_") or name == "PFM_CONFIG":
            continue
        remainder = name[4:].lower()
        matches = [
            section for section in data if remainder.startswith(section + "_")
        ]
        if not matches:
            continue
        section = max(matches, key=len)
        key = remainder[len(section) + 1 :]
        key = CONFIG_ALIASES.get(section, {}).get(key, key)
        current = data[section].get(key)
        if isinstance(current, bool):
            if raw.lower() not in {"true", "false", "1", "0", "yes", "no"}:
                raise ConfigurationError(f"{name} must be true or false")
            value: Any = raw.lower() in {"true", "1", "yes"}
        elif isinstance(current, int):
            value = int(raw)
        elif isinstance(current, float):
            value = float(raw)
        elif isinstance(current, (list, tuple)):
            value = [item.strip() for item in raw.split(",") if item.strip()]
        else:
            value = raw
        data[section][key] = value


def _path(value: Any, config_path: Path) -> Path:
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = (config_path.parent.parent / path).resolve()
    return path


def _bounded(name: str, value: Any, low: float, high: float) -> float:
    number = float(value)
    if not low <= number <= high:
        raise ConfigurationError(f"{name} must be between {low} and {high}")
    return number


def load_config(
    config_path: Path | None = None,
    environ: dict[str, str] | None = None,
) -> FieldMouseConfig:
    environ = dict(os.environ if environ is None else environ)
    selected = Path(
        config_path or environ.get("PFM_CONFIG", DEFAULT_CONFIG_PATH)
    ).resolve()
    values: dict[str, Any] = {}
    if selected.exists():
        try:
            with selected.open("rb") as stream:
                values = tomllib.load(stream)
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise ConfigurationError(f"Cannot read {selected}: {error}") from error
    elif config_path is not None or "PFM_CONFIG" in environ:
        raise ConfigurationError(f"Configuration file not found: {selected}")

    data = _merge(DEFAULTS, values)
    _migrate_compatibility_fields(data)
    # Dataclass defaults supply missing keys while still permitting env-only setup.
    prototypes = {
        "station": StationConfig(), "audio": AudioConfig(),
        "storage": StorageConfig(), "detection": DetectionConfig(),
        "birdnet": BirdNETConfig(), "dashboard": DashboardConfig(),
        "logging": LoggingConfig(), "health": HealthConfig(),
    }
    for section, prototype in prototypes.items():
        for key, value in prototype.__dict__.items():
            data[section].setdefault(key, value)
    _environment(data, environ)

    try:
        ZoneInfo(str(data["station"]["timezone"]))
        station_id = str(data["station"]["id"]).strip()
        station_name = str(data["station"]["name"]).strip()
        if not station_id or not station_name:
            raise ConfigurationError("station id and name cannot be empty")
        station = StationConfig(
            id=station_id, uuid=str(data["station"]["uuid"]), name=station_name,
            timezone=str(data["station"]["timezone"]),
            latitude=(None if data["station"]["latitude"] is None else
                      _bounded("station.latitude", data["station"]["latitude"], -90, 90)),
            longitude=(None if data["station"]["longitude"] is None else
                       _bounded("station.longitude", data["station"]["longitude"], -180, 180)),
            location_name=str(data["station"]["location_name"]),
            hardware_version=str(data["station"]["hardware_version"]),
            deployment_date=str(data["station"]["deployment_date"]),
            capabilities=tuple(data["station"]["capabilities"]),
        )
        audio = AudioConfig(**{
            **data["audio"],
            "sample_rate": int(data["audio"]["sample_rate"]),
            "channels": int(data["audio"]["channels"]),
            "recording_duration_seconds": int(data["audio"]["recording_duration_seconds"]),
            "recording_interval_seconds": int(data["audio"]["recording_interval_seconds"]),
        })
        if min(audio.sample_rate, audio.channels, audio.recording_duration_seconds,
               audio.recording_interval_seconds) < 1:
            raise ConfigurationError("audio numeric values must be positive")
        storage_values = dict(data["storage"])
        for key in ("recordings_directory", "database_path", "logs_directory", "backups_directory"):
            storage_values[key] = _path(storage_values[key], selected)
        storage_values["rare_species"] = tuple(
            storage_values["rare_species"]
        )
        storage = StorageConfig(**storage_values)
        detection = DetectionConfig(
            **{**data["detection"],
               "minimum_confidence": _bounded("detection.minimum_confidence",
                                               data["detection"]["minimum_confidence"], 0, 1),
               "species_include": tuple(data["detection"]["species_include"]),
               "species_exclude": tuple(data["detection"]["species_exclude"])}
        )
        birdnet = BirdNETConfig(
            **{**data["birdnet"],
               "minimum_confidence": _bounded("birdnet.minimum_confidence",
                                               data["birdnet"]["minimum_confidence"], 0, 1),
               "occurrence_threshold": _bounded("birdnet.occurrence_threshold",
                                                data["birdnet"]["occurrence_threshold"], 0, 1)}
        )
        dashboard = DashboardConfig(
            host=str(data["dashboard"]["host"]),
            port=int(data["dashboard"]["port"]),
        )
        if not 1 <= dashboard.port <= 65535:
            raise ConfigurationError("dashboard.port must be between 1 and 65535")
        logging = LoggingConfig(**data["logging"])
        if logging.level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigurationError("logging.level is invalid")
        health = HealthConfig(**{**data["health"], "services": tuple(data["health"]["services"])})
        thresholds = (
            health.disk_advisory_percent,
            health.disk_warning_percent,
            health.disk_critical_percent,
            health.disk_emergency_percent,
        )
        if not (
            0 < thresholds[0] < thresholds[1] < thresholds[2] < thresholds[3] < 100
        ):
            raise ConfigurationError(
                "health disk thresholds must increase from advisory to emergency"
            )
    except (TypeError, ValueError, ZoneInfoNotFoundError) as error:
        raise ConfigurationError(f"Invalid configuration: {error}") from error
    return FieldMouseConfig(station, audio, storage, detection, birdnet,
                            dashboard, logging, health)
