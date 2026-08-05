"""Hardware-free station simulator using synthetic sample audio and detections."""
from __future__ import annotations

import json
import math
import random
import struct
import uuid
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import FieldMouseConfig
from app.database.connection import connect_database
from app.metrics import record_metric
from app.migrations import migrate

SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "detections.json"
MODES = ("samples", "detections", "high", "low", "offline", "errors")


def _exercise_verification(
    connection,
    config: FieldMouseConfig,
    detection_id: int,
    recording_id: int,
    item: dict,
    confidence: float,
    recorded: datetime,
    audio: Path,
) -> bool:
    """Use the verification public API when that optional feature is installed."""
    try:
        from app.verification.manager import VerificationManager
        from app.verification.models import DetectionContext
    except ImportError:
        return False
    from app.metrics import measure
    context = DetectionContext(
        detection_id=detection_id, recording_id=recording_id,
        station_id=config.station.id, scientific_name=item["scientific_name"],
        common_name=item["common_name"], birdnet_confidence=confidence,
        recorded_at=recorded, audio_path=audio,
        latitude=config.station.latitude, longitude=config.station.longitude,
        metadata={"simulation": True},
    )
    with measure(connection, config.station.id, "verification_execution"):
        VerificationManager(plugins=()).verify(context)
    return True


def _sample_wav(path: Path, seconds: float = 1.0, frequency: int = 880) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 8_000
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        frames = (
            struct.pack("<h", int(5000 * math.sin(2 * math.pi * frequency * index / rate)))
            for index in range(int(rate * seconds))
        )
        output.writeframes(b"".join(frames))


def simulate(config: FieldMouseConfig, mode: str, count: int | None = None, seed: int = 42) -> dict:
    if mode not in MODES:
        raise ValueError(f"Unknown simulation mode: {mode}")
    migrate(config.storage.database_path, config.storage.backups_directory)
    samples = json.loads(SAMPLES.read_text(encoding="utf-8"))
    randomizer = random.Random(seed)
    total = count if count is not None else {"high": 60, "low": 3}.get(mode, 12)
    if mode == "offline":
        total = 0
    station_uuid = config.station.uuid or str(uuid.uuid5(uuid.NAMESPACE_URL, config.station.id))
    created = 0
    detections = 0
    verified = 0
    with connect_database(config.storage.database_path) as connection:
        connection.execute(
            """INSERT INTO stations
            (id,name,timezone,created_at,station_uuid,hardware_version,software_version,
             deployment_date,location_name,latitude,longitude,capabilities)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET name=excluded.name, station_uuid=excluded.station_uuid""",
            (config.station.id, config.station.name, config.station.timezone,
             datetime.now(timezone.utc).isoformat(), station_uuid,
             config.station.hardware_version, "simulation", config.station.deployment_date,
             config.station.location_name, config.station.latitude, config.station.longitude,
             json.dumps(config.station.capabilities)),
        )
        for index in range(total):
            recorded = datetime.now(timezone.utc) - timedelta(minutes=(total - index) * 5)
            audio = (
                config.storage.recordings_directory / config.station.id / "simulation" /
                f"{recorded:%Y%m%dT%H%M%S}-{index}.wav"
            )
            _sample_wav(audio, frequency=600 + (index % 5) * 100)
            status = "failed" if mode == "errors" and index % 3 == 0 else "processed"
            cursor = connection.execute(
                """INSERT INTO recordings
                (station_id,file_path,recorded_at,duration_seconds,sample_rate,channels,
                 sample_format,file_size_bytes,processing_status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (config.station.id, str(audio), recorded.isoformat(), 1, 8000, 1, "S16_LE",
                 audio.stat().st_size, status, recorded.isoformat()),
            )
            created += 1
            if mode not in {"samples", "offline"} or index % 2 == 0:
                item = randomizer.choice(samples)
                confidence = randomizer.uniform(*item["confidence"])
                detection = connection.execute(
                    """INSERT INTO detections
                    (recording_id,detector,common_name,scientific_name,confidence,start_time,end_time,created_at)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (cursor.lastrowid, "simulator", item["common_name"], item["scientific_name"],
                     confidence, 0.1, 0.9, recorded.isoformat()),
                )
                detections += 1
                if _exercise_verification(
                    connection, config, int(detection.lastrowid), int(cursor.lastrowid),
                    item, confidence, recorded, audio,
                ):
                    verified += 1
            record_metric(connection, config.station.id, "recording_duration", 1000, "milliseconds",
                          {"simulated": True})
        connection.commit()
    return {"mode": mode, "recordings": created, "detections": detections,
            "verification_exercised": verified,
            "database": str(config.storage.database_path)}
