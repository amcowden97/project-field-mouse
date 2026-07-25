from __future__ import annotations

import argparse
import subprocess
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fieldmouse.config import (
    ConfigurationError,
    FieldMouseConfig,
    load_config,
)
from fieldmouse.database import (
    DatabaseError,
    connect_database,
    initialize_database,
    insert_recording,
    upsert_station,
)


def get_station_time(config: FieldMouseConfig) -> datetime:
    try:
        timezone = ZoneInfo(config.station.timezone)
    except ZoneInfoNotFoundError as error:
        raise ConfigurationError(
            f"Unknown station timezone: {config.station.timezone}"
        ) from error

    return datetime.now(timezone)


def create_recording_path(
    recordings_root: Path,
    station_id: str,
    recorded_at: datetime,
) -> Path:
    date_directory = (
        recordings_root
        / station_id
        / recorded_at.strftime("%Y-%m-%d")
    )

    date_directory.mkdir(parents=True, exist_ok=True)

    filename = recorded_at.strftime("%Y-%m-%dT%H-%M-%S%z.wav")
    return date_directory / filename


def build_arecord_command(
    config: FieldMouseConfig,
    output_path: Path,
    duration_seconds: int,
) -> list[str]:
    return [
        "arecord",
        "-D",
        config.audio.device,
        "-f",
        config.audio.sample_format,
        "-r",
        str(config.audio.sample_rate),
        "-c",
        str(config.audio.channels),
        "-d",
        str(duration_seconds),
        str(output_path),
    ]


def validate_recording(output_path: Path) -> int:
    if not output_path.exists():
        raise RuntimeError(
            "Recording completed, but no output file was created."
        )

    file_size_bytes = output_path.stat().st_size

    if file_size_bytes <= 44:
        raise RuntimeError(
            "Recording file contains no usable audio data."
        )

    return file_size_bytes


def save_recording_to_database(
    *,
    config: FieldMouseConfig,
    output_path: Path,
    recorded_at: datetime,
    duration_seconds: int,
    file_size_bytes: int,
) -> int:
    initialize_database(config.storage.database_path)

    with closing(
        connect_database(config.storage.database_path)
    ) as connection:
        upsert_station(connection, config)

        recording_id = insert_recording(
            connection,
            station_id=config.station.id,
            file_path=output_path,
            recorded_at=recorded_at.isoformat(),
            duration_seconds=duration_seconds,
            sample_rate=config.audio.sample_rate,
            channels=config.audio.channels,
            sample_format=config.audio.sample_format,
            file_size_bytes=file_size_bytes,
        )

        connection.commit()

    return recording_id


def record_audio(
    config: FieldMouseConfig,
    duration_override: int | None = None,
) -> Path:
    duration_seconds = (
        duration_override
        if duration_override is not None
        else config.audio.recording_duration_seconds
    )

    if duration_seconds <= 0:
        raise ValueError(
            "Recording duration must be greater than zero."
        )

    recorded_at = get_station_time(config)

    output_path = create_recording_path(
        recordings_root=config.storage.recordings_directory,
        station_id=config.station.id,
        recorded_at=recorded_at,
    )

    command = build_arecord_command(
        config=config,
        output_path=output_path,
        duration_seconds=duration_seconds,
    )

    print(f"Station: {config.station.name}")
    print(f"Station ID: {config.station.id}")
    print(f"Recorded at: {recorded_at.isoformat()}")
    print(f"Audio device: {config.audio.device}")
    print(f"Duration: {duration_seconds} seconds")
    print(f"Output: {output_path}")

    try:
        subprocess.run(
            command,
            check=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError(
            "The arecord command is not installed."
        ) from error
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            f"Recording failed with exit code {error.returncode}."
        ) from error

    try:
        file_size_bytes = validate_recording(output_path)

        recording_id = save_recording_to_database(
            config=config,
            output_path=output_path,
            recorded_at=recorded_at,
            duration_seconds=duration_seconds,
            file_size_bytes=file_size_bytes,
        )
    except Exception:
        output_path.unlink(missing_ok=True)
        raise

    print(f"Recording complete: {file_size_bytes:,} bytes")
    print(f"Database recording ID: {recording_id}")

    return output_path


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record audio for Project Field Mouse."
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/station.toml"),
        help="Path to the station TOML configuration file.",
    )

    parser.add_argument(
        "--duration",
        type=int,
        help="Override the configured recording duration.",
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    try:
        config = load_config(arguments.config)

        record_audio(
            config=config,
            duration_override=arguments.duration,
        )
    except (
        ConfigurationError,
        DatabaseError,
        RuntimeError,
        ValueError,
    ) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
