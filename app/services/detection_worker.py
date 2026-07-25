from __future__ import annotations

import argparse
import signal
import sqlite3
import time
from pathlib import Path

from app.detectors.process_recording import (
    DEFAULT_CONFIDENCE,
    DEFAULT_DATABASE,
    DEFAULT_LATITUDE,
    DEFAULT_LONGITUDE,
    DEFAULT_OCCURRENCE_THRESHOLD,
    connect_database,
    get_recording,
    resolve_audio_path,
    run_birdnet,
    save_detections,
)


_stop_requested = False


def request_stop(
    signal_number: int,
    frame: object,
) -> None:
    del signal_number
    del frame

    global _stop_requested
    _stop_requested = True

    print()
    print("BirdNET worker stopping after the current cycle...")


def has_pending_recording(
    connection: sqlite3.Connection,
) -> bool:
    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(recordings)"
        ).fetchall()
    }

    if "processing_status" in columns:
        row = connection.execute(
            """
            SELECT 1
            FROM recordings
            WHERE processing_status = 'pending'
            LIMIT 1
            """
        ).fetchone()

        return row is not None

    if "status" in columns:
        row = connection.execute(
            """
            SELECT 1
            FROM recordings
            WHERE status = 'pending'
            LIMIT 1
            """
        ).fetchone()

        return row is not None

    return False


def process_next_recording(
    *,
    database_path: Path,
    minimum_confidence: float,
    latitude: float,
    longitude: float,
    occurrence_threshold: float,
) -> bool:
    connection = connect_database(database_path)

    try:
        if not has_pending_recording(connection):
            return False

        recording = get_recording(
            connection,
            recording_id=None,
        )

        recording_id = int(recording["id"])
        audio_path = resolve_audio_path(
            recording["audio_path"]
        )

        print()
        print(f"Processing recording ID: {recording_id}")
        print(f"Audio: {audio_path}")

        predictions = run_birdnet(
            audio_path,
            latitude=latitude,
            longitude=longitude,
            occurrence_threshold=occurrence_threshold,
        )

        saved_count = save_detections(
            connection,
            recording_id,
            predictions,
            minimum_confidence,
        )

        print(
            f"Recording {recording_id} complete: "
            f"{saved_count} detection(s) saved."
        )

        return True
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Continuously process pending recordings "
            "with BirdNET."
        )
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
    )

    parser.add_argument(
        "--minimum-confidence",
        type=float,
        default=DEFAULT_CONFIDENCE,
    )

    parser.add_argument(
        "--latitude",
        type=float,
        default=DEFAULT_LATITUDE,
    )

    parser.add_argument(
        "--longitude",
        type=float,
        default=DEFAULT_LONGITUDE,
    )

    parser.add_argument(
        "--occurrence-threshold",
        type=float,
        default=DEFAULT_OCCURRENCE_THRESHOLD,
    )

    parser.add_argument(
        "--poll-interval",
        type=float,
        default=10.0,
        help=(
            "Seconds to wait when no pending recording exists."
        ),
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one pending recording.",
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    if not 0.0 <= arguments.minimum_confidence <= 1.0:
        raise ValueError(
            "Minimum confidence must be between 0 and 1."
        )

    if not 0.0 <= arguments.occurrence_threshold <= 1.0:
        raise ValueError(
            "Occurrence threshold must be between 0 and 1."
        )

    if arguments.poll_interval <= 0:
        raise ValueError(
            "Poll interval must be greater than zero."
        )

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    print("Project Field Mouse BirdNET worker starting")
    print(f"Database: {arguments.database}")
    print(
        "Minimum confidence: "
        f"{arguments.minimum_confidence:.0%}"
    )
    print(
        "Location: "
        f"{arguments.latitude}, {arguments.longitude}"
    )
    print(
        "Occurrence threshold: "
        f"{arguments.occurrence_threshold:.0%}"
    )

    while not _stop_requested:
        processed = process_next_recording(
            database_path=arguments.database,
            minimum_confidence=(
                arguments.minimum_confidence
            ),
            latitude=arguments.latitude,
            longitude=arguments.longitude,
            occurrence_threshold=(
                arguments.occurrence_threshold
            ),
        )

        if arguments.once:
            if not processed:
                print("No pending recording found.")

            break

        if not processed:
            time.sleep(arguments.poll_interval)

    print("BirdNET worker stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
