from __future__ import annotations

import argparse
import signal
import sqlite3
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from datetime import datetime, time as clock_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


DEFAULT_CONFIG = Path("config/station.toml")

_stop_requested = False


@dataclass(frozen=True)
class AdaptiveSettings:
    timezone: str
    database_path: Path
    enabled: bool

    dawn_start: clock_time
    dawn_end: clock_time
    evening_start: clock_time
    evening_end: clock_time

    dawn_interval_seconds: int
    day_interval_seconds: int
    evening_interval_seconds: int
    night_interval_seconds: int

    burst_enabled: bool
    burst_interval_seconds: int
    burst_duration_minutes: int
    burst_minimum_confidence: float


def request_stop(
    signal_number: int,
    frame: object,
) -> None:
    del signal_number
    del frame

    global _stop_requested
    _stop_requested = True

    print()
    print("Adaptive recorder will stop after the current recording.")


def parse_clock(value: str) -> clock_time:
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as error:
        raise ValueError(
            f"Invalid clock time {value!r}; expected HH:MM."
        ) from error


def load_settings(config_path: Path) -> AdaptiveSettings:
    with config_path.open("rb") as file:
        config = tomllib.load(file)

    station = config.get("station", {})
    storage = config.get("storage", {})
    adaptive = config.get("adaptive_recording", {})

    database_path = Path(
        storage.get(
            "database_path",
            "data/database/fieldmouse.db",
        )
    )

    return AdaptiveSettings(
        timezone=str(
            station.get(
                "timezone",
                "America/Los_Angeles",
            )
        ),
        database_path=database_path,
        enabled=bool(adaptive.get("enabled", True)),
        dawn_start=parse_clock(
            str(adaptive.get("dawn_start", "05:00"))
        ),
        dawn_end=parse_clock(
            str(adaptive.get("dawn_end", "09:00"))
        ),
        evening_start=parse_clock(
            str(adaptive.get("evening_start", "17:00"))
        ),
        evening_end=parse_clock(
            str(adaptive.get("evening_end", "21:00"))
        ),
        dawn_interval_seconds=int(
            adaptive.get(
                "dawn_interval_seconds",
                120,
            )
        ),
        day_interval_seconds=int(
            adaptive.get(
                "day_interval_seconds",
                300,
            )
        ),
        evening_interval_seconds=int(
            adaptive.get(
                "evening_interval_seconds",
                300,
            )
        ),
        night_interval_seconds=int(
            adaptive.get(
                "night_interval_seconds",
                900,
            )
        ),
        burst_enabled=bool(
            adaptive.get("burst_enabled", True)
        ),
        burst_interval_seconds=int(
            adaptive.get(
                "burst_interval_seconds",
                60,
            )
        ),
        burst_duration_minutes=int(
            adaptive.get(
                "burst_duration_minutes",
                20,
            )
        ),
        burst_minimum_confidence=float(
            adaptive.get(
                "burst_minimum_confidence",
                0.50,
            )
        ),
    )


def validate_settings(settings: AdaptiveSettings) -> None:
    intervals = {
        "dawn_interval_seconds":
            settings.dawn_interval_seconds,
        "day_interval_seconds":
            settings.day_interval_seconds,
        "evening_interval_seconds":
            settings.evening_interval_seconds,
        "night_interval_seconds":
            settings.night_interval_seconds,
        "burst_interval_seconds":
            settings.burst_interval_seconds,
    }

    for name, value in intervals.items():
        if value <= 0:
            raise ValueError(
                f"{name} must be greater than zero."
            )

    if settings.burst_duration_minutes < 0:
        raise ValueError(
            "burst_duration_minutes cannot be negative."
        )

    if not 0 <= settings.burst_minimum_confidence <= 1:
        raise ValueError(
            "burst_minimum_confidence must be between 0 and 1."
        )


def is_between(
    value: clock_time,
    start: clock_time,
    end: clock_time,
) -> bool:
    if start <= end:
        return start <= value < end

    # Supports a range crossing midnight.
    return value >= start or value < end


def latest_qualifying_detection(
    settings: AdaptiveSettings,
    now: datetime,
) -> datetime | None:
    if (
        not settings.burst_enabled
        or not settings.database_path.exists()
    ):
        return None

    connection = sqlite3.connect(
        settings.database_path
    )

    try:
        row = connection.execute(
            """
            SELECT r.recorded_at
            FROM detections AS d
            JOIN recordings AS r
                ON r.id = d.recording_id
            WHERE d.confidence >= ?
            ORDER BY r.recorded_at DESC
            LIMIT 1
            """,
            (settings.burst_minimum_confidence,),
        ).fetchone()
    except sqlite3.Error as error:
        print(
            "Could not inspect recent detections: "
            f"{error}"
        )
        return None
    finally:
        connection.close()

    if row is None or row[0] is None:
        return None

    raw_timestamp = str(row[0]).replace(
        "Z",
        "+00:00",
    )

    try:
        detected_at = datetime.fromisoformat(
            raw_timestamp
        )
    except ValueError:
        return None

    timezone = ZoneInfo(settings.timezone)

    if detected_at.tzinfo is None:
        detected_at = detected_at.replace(
            tzinfo=timezone
        )
    else:
        detected_at = detected_at.astimezone(
            timezone
        )

    maximum_age = timedelta(
        minutes=settings.burst_duration_minutes
    )

    if now - detected_at <= maximum_age:
        return detected_at

    return None


def choose_interval(
    settings: AdaptiveSettings,
    now: datetime,
) -> tuple[int, str]:
    recent_detection = latest_qualifying_detection(
        settings,
        now,
    )

    if recent_detection is not None:
        return (
            settings.burst_interval_seconds,
            (
                "bird activity burst; last qualifying "
                f"detection at "
                f"{recent_detection.strftime('%H:%M:%S')}"
            ),
        )

    local_time = now.time()

    if is_between(
        local_time,
        settings.dawn_start,
        settings.dawn_end,
    ):
        return (
            settings.dawn_interval_seconds,
            "dawn schedule",
        )

    if is_between(
        local_time,
        settings.evening_start,
        settings.evening_end,
    ):
        return (
            settings.evening_interval_seconds,
            "evening schedule",
        )

    if (
        settings.dawn_end
        <= local_time
        < settings.evening_start
    ):
        return (
            settings.day_interval_seconds,
            "day schedule",
        )

    return (
        settings.night_interval_seconds,
        "night schedule",
    )


def run_one_recording(config_path: Path) -> int:
    command = [
        sys.executable,
        "-m",
        "fieldmouse.services.scheduler",
        "--config",
        str(config_path),
        "--once",
    ]

    print("Starting one recording...")

    completed = subprocess.run(
        command,
        check=False,
    )

    if completed.returncode != 0:
        print(
            "Recorder exited with status "
            f"{completed.returncode}."
        )

    return completed.returncode


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run Project Field Mouse using an adaptive "
            "recording schedule."
        )
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "Make one recording and print the next "
            "selected interval."
        ),
    )

    parser.add_argument(
        "--show-schedule",
        action="store_true",
        help=(
            "Print the interval currently selected "
            "without recording."
        ),
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    settings = load_settings(arguments.config)
    validate_settings(settings)

    timezone = ZoneInfo(settings.timezone)

    if arguments.show_schedule:
        now = datetime.now(timezone)
        interval, reason = choose_interval(
            settings,
            now,
        )

        print(
            f"Current schedule: every {interval} seconds"
        )
        print(f"Reason: {reason}")
        return 0

    if not settings.enabled:
        print(
            "Adaptive recording is disabled in the "
            "station configuration."
        )
        return 1

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    print("Project Field Mouse adaptive recorder starting")
    print(f"Timezone: {settings.timezone}")
    print(f"Database: {settings.database_path}")

    while not _stop_requested:
        cycle_started = time.monotonic()

        return_code = run_one_recording(
            arguments.config
        )

        now = datetime.now(timezone)
        interval, reason = choose_interval(
            settings,
            now,
        )

        elapsed = time.monotonic() - cycle_started
        sleep_seconds = max(
            interval - elapsed,
            1,
        )

        print(
            f"Next recording in {sleep_seconds:.0f} seconds "
            f"({reason})."
        )

        if arguments.once:
            return return_code

        deadline = time.monotonic() + sleep_seconds

        while (
            not _stop_requested
            and time.monotonic() < deadline
        ):
            time.sleep(
                min(
                    1,
                    deadline - time.monotonic(),
                )
            )

    print("Adaptive recorder stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
