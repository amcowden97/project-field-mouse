from __future__ import annotations

import csv
import tempfile
from datetime import datetime
from pathlib import Path

import birdnet


DEFAULT_LATITUDE = 47.5673
DEFAULT_LONGITUDE = -122.6326
DEFAULT_OCCURRENCE_THRESHOLD = 0.03


def get_week_for_recording(audio_path: Path) -> int:
    modified_at = datetime.fromtimestamp(
        audio_path.stat().st_mtime
    )

    return modified_at.isocalendar().week


def create_local_species_list(
    *,
    latitude: float,
    longitude: float,
    week: int,
    occurrence_threshold: float,
) -> Path:
    print("Loading BirdNET geographic model...")
    geo_model = birdnet.load("geo", "2.4", "tf")

    print(
        "Predicting locally plausible species for "
        f"latitude={latitude}, longitude={longitude}, "
        f"week={week}..."
    )

    predictions = geo_model.predict(
        latitude,
        longitude,
        week=week,
    )

    with tempfile.NamedTemporaryFile(
        suffix=".csv",
        delete=False,
    ) as temporary_csv:
        csv_path = Path(temporary_csv.name)

    with tempfile.NamedTemporaryFile(
        suffix=".txt",
        delete=False,
        mode="w",
        encoding="utf-8",
    ) as temporary_species_file:
        species_path = Path(temporary_species_file.name)

    try:
        predictions.to_csv(str(csv_path))

        selected_species: list[str] = []

        with csv_path.open(
            newline="",
            encoding="utf-8",
        ) as csv_file:
            for row in csv.DictReader(csv_file):
                confidence = float(row["confidence"])

                if confidence >= occurrence_threshold:
                    selected_species.append(
                        row["species_name"].strip()
                    )

        selected_species = sorted(set(selected_species))

        if not selected_species:
            raise RuntimeError(
                "The geographic model returned no species "
                "above the occurrence threshold."
            )

        species_path.write_text(
            "\n".join(selected_species) + "\n",
            encoding="utf-8",
        )

        print(
            f"Using {len(selected_species)} locally plausible "
            "species."
        )

        return species_path
    finally:
        csv_path.unlink(missing_ok=True)
