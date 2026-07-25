from __future__ import annotations

import argparse
from pathlib import Path

import birdnet


def find_latest_recording(recordings_directory: Path) -> Path:
    recordings = list(recordings_directory.rglob("*.wav"))

    if not recordings:
        raise FileNotFoundError(
            f"No WAV files found under {recordings_directory}"
        )

    return max(recordings, key=lambda path: path.stat().st_mtime)


def analyze_recording(audio_path: Path, output_path: Path) -> None:
    print("Loading BirdNET model...")
    model = birdnet.load("acoustic", "2.4", "tf")

    print(f"Analyzing: {audio_path}")
    predictions = model.predict(str(audio_path))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(str(output_path))

    print(f"Results saved to: {output_path}")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze a WAV recording with BirdNET."
    )

    parser.add_argument(
        "audio_file",
        nargs="?",
        type=Path,
        help="WAV file to analyze. Defaults to the newest recording.",
    )

    parser.add_argument(
        "--recordings-directory",
        type=Path,
        default=Path("data/recordings"),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/detections/latest-birdnet-results.csv"),
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    audio_path = (
        arguments.audio_file
        if arguments.audio_file
        else find_latest_recording(arguments.recordings_directory)
    )

    if not audio_path.exists():
        raise FileNotFoundError(
            f"Audio file does not exist: {audio_path}"
        )

    analyze_recording(audio_path, arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
