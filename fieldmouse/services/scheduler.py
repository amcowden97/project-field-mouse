from __future__ import annotations

import argparse
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from threading import Event, Lock

from fieldmouse.audio.recorder import record_audio
from fieldmouse.config import (
    ConfigurationError,
    FieldMouseConfig,
    load_config,
)
from fieldmouse.database import DatabaseError


shutdown_event = Event()
recording_lock = Lock()


def handle_shutdown(signum: int, frame: object) -> None:
    signal_name = signal.Signals(signum).name
    print(f"\nReceived {signal_name}. Shutting down cleanly...")
    shutdown_event.set()


def run_recording_cycle(config: FieldMouseConfig) -> None:
    if not recording_lock.acquire(blocking=False):
        print("Skipping cycle because a recording is already in progress.")
        return

    try:
        started_at = datetime.now().isoformat(timespec="seconds")
        print(f"\nStarting recording cycle at {started_at}")

        output_path = record_audio(config)

        print(f"Cycle completed successfully: {output_path}")
    except (
        ConfigurationError,
        DatabaseError,
        RuntimeError,
        ValueError,
    ) as error:
        print(f"Recording cycle failed: {error}", file=sys.stderr)
    finally:
        recording_lock.release()


def run_scheduler(
    config: FieldMouseConfig,
    *,
    run_immediately: bool = True,
    once: bool = False,
) -> None:
    interval_seconds = config.audio.recording_interval_seconds

    print("Project Field Mouse scheduler starting")
    print(f"Station: {config.station.name}")
    print(f"Interval: {interval_seconds} seconds")
    print(
        f"Recording duration: "
        f"{config.audio.recording_duration_seconds} seconds"
    )

    if (
        config.audio.recording_duration_seconds
        >= interval_seconds
    ):
        raise ValueError(
            "Recording duration must be shorter than the recording interval."
        )

    if run_immediately:
        run_recording_cycle(config)

        if once:
            return

    next_run = time.monotonic() + interval_seconds

    while not shutdown_event.is_set():
        remaining_seconds = next_run - time.monotonic()

        if remaining_seconds > 0:
            shutdown_event.wait(
                timeout=min(remaining_seconds, 1.0)
            )
            continue

        run_recording_cycle(config)

        next_run += interval_seconds

        current_time = time.monotonic()

        if next_run <= current_time:
            missed_intervals = (
                int((current_time - next_run) // interval_seconds)
                + 1
            )

            next_run += missed_intervals * interval_seconds

            print(
                f"Skipped {missed_intervals} missed interval(s) "
                "to avoid overlapping catch-up recordings."
            )

    print("Scheduler stopped.")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Project Field Mouse recording scheduler."
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/station.toml"),
        help="Path to the station configuration file.",
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Create one recording and exit.",
    )

    parser.add_argument(
        "--wait-first",
        action="store_true",
        help="Wait one interval before the first recording.",
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        config = load_config(arguments.config)

        run_scheduler(
            config,
            run_immediately=not arguments.wait_first,
            once=arguments.once,
        )
    except (
        ConfigurationError,
        ValueError,
    ) as error:
        print(f"Scheduler error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
