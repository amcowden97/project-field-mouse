from __future__ import annotations

import argparse
import csv
import sqlite3
import tempfile
from pathlib import Path

import birdnet

from app.detectors.local_species import (
    DEFAULT_LATITUDE,
    DEFAULT_LONGITUDE,
    DEFAULT_OCCURRENCE_THRESHOLD,
    create_local_species_list,
    get_week_for_recording,
)


DEFAULT_DATABASE = Path("data/database/fieldmouse.db")
DEFAULT_CONFIDENCE = 0.25


def connect_database(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def get_recordings_columns(
    connection: sqlite3.Connection,
) -> set[str]:
    rows = connection.execute(
        "PRAGMA table_info(recordings)"
    ).fetchall()

    return {row["name"] for row in rows}


def get_recording_path_column(
    connection: sqlite3.Connection,
) -> str:
    columns = get_recordings_columns(connection)

    possible_columns = (
        "path",
        "file_path",
        "audio_path",
        "recording_path",
        "filename",
    )

    for column in possible_columns:
        if column in columns:
            return column

    raise RuntimeError(
        "Could not find a recording file path column. "
        f"Available columns: {sorted(columns)}"
    )


def get_recording(
    connection: sqlite3.Connection,
    recording_id: int | None,
) -> sqlite3.Row:
    columns = get_recordings_columns(connection)
    path_column = get_recording_path_column(connection)

    if recording_id is not None:
        query = f"""
            SELECT id, {path_column} AS audio_path
            FROM recordings
            WHERE id = ?
        """

        recording = connection.execute(
            query,
            (recording_id,),
        ).fetchone()

    elif "processing_status" in columns:
        query = f"""
            SELECT id, {path_column} AS audio_path
            FROM recordings
            WHERE processing_status = 'pending'
            ORDER BY id ASC
            LIMIT 1
        """

        recording = connection.execute(query).fetchone()

    elif "status" in columns:
        query = f"""
            SELECT id, {path_column} AS audio_path
            FROM recordings
            WHERE status = 'pending'
            ORDER BY id ASC
            LIMIT 1
        """

        recording = connection.execute(query).fetchone()

    else:
        query = f"""
            SELECT id, {path_column} AS audio_path
            FROM recordings
            ORDER BY id DESC
            LIMIT 1
        """

        recording = connection.execute(query).fetchone()

    if recording is None:
        raise RuntimeError("No eligible recording was found.")

    return recording


def resolve_audio_path(stored_path: str) -> Path:
    audio_path = Path(stored_path)

    if not audio_path.is_absolute():
        audio_path = Path.cwd() / audio_path

    audio_path = audio_path.resolve()

    if not audio_path.exists():
        raise FileNotFoundError(
            f"Recording file does not exist: {audio_path}"
        )

    return audio_path


def split_species_name(
    species_name: str,
) -> tuple[str | None, str]:
    if "_" not in species_name:
        return None, species_name.strip()

    scientific_name, common_name = species_name.split("_", 1)

    return scientific_name.strip(), common_name.strip()


def run_birdnet(
    audio_path: Path,
    latitude: float,
    longitude: float,
    occurrence_threshold: float,
) -> list[dict[str, str]]:
    week = get_week_for_recording(audio_path)

    species_path = create_local_species_list(
        latitude=latitude,
        longitude=longitude,
        week=week,
        occurrence_threshold=occurrence_threshold,
    )

    try:
        print("Loading BirdNET acoustic model...")
        model = birdnet.load("acoustic", "2.4", "tf")

        print(f"Analyzing {audio_path}...")

        predictions = model.predict(
            str(audio_path),
            custom_species_list=str(species_path),
        )

        with tempfile.NamedTemporaryFile(
            suffix=".csv",
            delete=False,
        ) as temporary_file:
            csv_path = Path(temporary_file.name)

        try:
            predictions.to_csv(str(csv_path))

            with csv_path.open(
                newline="",
                encoding="utf-8",
            ) as csv_file:
                return list(csv.DictReader(csv_file))
        finally:
            csv_path.unlink(missing_ok=True)
    finally:
        species_path.unlink(missing_ok=True)


def save_detections(
    connection: sqlite3.Connection,
    recording_id: int,
    predictions: list[dict[str, str]],
    minimum_confidence: float,
) -> int:
    saved_count = 0

    connection.execute(
        """
        DELETE FROM detections
        WHERE recording_id = ?
          AND detector = 'birdnet'
        """,
        (recording_id,),
    )

    for prediction in predictions:
        confidence = float(prediction["confidence"])

        if confidence < minimum_confidence:
            continue

        scientific_name, common_name = split_species_name(
            prediction["species_name"]
        )

        connection.execute(
            """
            INSERT INTO detections (
                recording_id,
                detector,
                scientific_name,
                common_name,
                confidence,
                start_time,
                end_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recording_id,
                "birdnet",
                scientific_name,
                common_name,
                confidence,
                prediction["start_time"],
                prediction["end_time"],
            ),
        )

        saved_count += 1

    update_recording_status(connection, recording_id)
    connection.commit()

    return saved_count


def update_recording_status(
    connection: sqlite3.Connection,
    recording_id: int,
) -> None:
    columns = get_recordings_columns(connection)

    if "processing_status" in columns:
        connection.execute(
            """
            UPDATE recordings
            SET processing_status = 'processed'
            WHERE id = ?
            """,
            (recording_id,),
        )
    elif "status" in columns:
        connection.execute(
            """
            UPDATE recordings
            SET status = 'processed'
            WHERE id = ?
            """,
            (recording_id,),
        )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze a recording with BirdNET and save "
            "detections to SQLite."
        )
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
    )

    parser.add_argument(
        "--recording-id",
        type=int,
        help=(
            "Recording to process. Defaults to the oldest "
            "pending recording."
        ),
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
        help="Approximate station latitude.",
    )

    parser.add_argument(
        "--longitude",
        type=float,
        default=DEFAULT_LONGITUDE,
        help="Approximate station longitude.",
    )

    parser.add_argument(
        "--occurrence-threshold",
        type=float,
        default=DEFAULT_OCCURRENCE_THRESHOLD,
        help=(
            "Minimum geographic occurrence score required "
            "for a species to be considered locally plausible."
        ),
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    if not 0.0 <= arguments.minimum_confidence <= 1.0:
        raise ValueError(
            "Minimum confidence must be between 0 and 1."
        )

    connection = connect_database(arguments.database)

    try:
        recording = get_recording(
            connection,
            arguments.recording_id,
        )

        recording_id = int(recording["id"])
        audio_path = resolve_audio_path(recording["audio_path"])

        print(f"Recording ID: {recording_id}")

        predictions = run_birdnet(
            audio_path,
            latitude=arguments.latitude,
            longitude=arguments.longitude,
            occurrence_threshold=(
                arguments.occurrence_threshold
            ),
        )

        saved_count = save_detections(
            connection,
            recording_id,
            predictions,
            arguments.minimum_confidence,
        )

        print(
            f"Saved {saved_count} detection(s) with confidence "
            f">= {arguments.minimum_confidence:.0%}."
        )
    finally:
        connection.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
