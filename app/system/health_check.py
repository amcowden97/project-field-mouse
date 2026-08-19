"""Portable station health probes and command-line diagnostics."""
from __future__ import annotations

import argparse
import json
import shutil
import socket
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

from app.config import FieldMouseConfig, load_config
from app.system.storage_health import storage_forecast, storage_state


def _timestamp_age(value: str | None) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())
    except ValueError:
        return None


def _service(name: str) -> dict[str, Any]:
    if shutil.which("systemctl") is None:
        return {"status": "unknown", "detail": "systemd unavailable"}
    try:
        result = subprocess.run(
            ["systemctl", "is-active", name], capture_output=True, text=True,
            timeout=3, check=False,
        )
        state = (result.stdout or result.stderr).strip() or "unknown"
        return {"status": "ok" if state == "active" else "error", "detail": state}
    except (OSError, subprocess.SubprocessError) as error:
        return {"status": "unknown", "detail": str(error)}


def _cleanup_freshness() -> dict[str, Any]:
    if shutil.which("systemctl") is None:
        return {"status": "unknown", "detail": "systemd unavailable"}
    try:
        result = subprocess.run(
            [
                "systemctl", "show", "fieldmouse-cleanup.service",
                "--property=Result,ExecMainStatus,ExecMainExitTimestamp,"
                "ExecMainExitTimestampMonotonic",
                "--no-pager",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        values = dict(
            line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
        )
        timestamp = values.get("ExecMainExitTimestamp") or None
        monotonic_raw = values.get("ExecMainExitTimestampMonotonic") or ""
        age = None
        if monotonic_raw.isdigit() and int(monotonic_raw) > 0:
            age = max(0.0, time.monotonic() - int(monotonic_raw) / 1_000_000)
        return {
            "status": "ok"
            if values.get("Result") in {"success", ""}
            and values.get("ExecMainStatus") in {"0", ""}
            else "error",
            "result": values.get("Result") or None,
            "exit_status": values.get("ExecMainStatus") or None,
            "last_completed_at": timestamp,
            "age_seconds": age,
        }
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        return {"status": "unknown", "detail": str(error)}


def _temperature() -> float | None:
    thermal = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        return round(float(thermal.read_text().strip()) / 1000, 1)
    except (OSError, ValueError):
        sensor_reader = getattr(psutil, "sensors_temperatures", None)
        if sensor_reader is None:
            return None
        temperatures = sensor_reader()
        for entries in temperatures.values():
            if entries:
                return round(float(entries[0].current), 1)
    return None


def _database(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"status": "error", "detail": "database missing"}
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3)
        integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
        failed = connection.execute(
            "SELECT COUNT(*) FROM recordings WHERE processing_status = 'failed'"
        ).fetchone()[0]
        latest = connection.execute(
            "SELECT MAX(recorded_at) FROM recordings"
        ).fetchone()[0]
        recording_count = connection.execute(
            "SELECT COUNT(*) FROM recordings"
        ).fetchone()[0]
        latest_processed = connection.execute(
            "SELECT MAX(recorded_at) FROM recordings "
            "WHERE processing_status IN ('processed', 'audio_expired')"
        ).fetchone()[0]
        latest_detection = connection.execute(
            "SELECT MAX(created_at) FROM detections"
        ).fetchone()[0]
        queue_depth = connection.execute(
            "SELECT COUNT(*) FROM recordings "
            "WHERE processing_status IN ('pending', 'processing')"
        ).fetchone()[0]
        recent = connection.execute(
            "SELECT recorded_at, file_size_bytes FROM recordings "
            "WHERE processing_status = 'processed' "
            "ORDER BY recorded_at DESC LIMIT 100"
        ).fetchall()
        connection.close()
        rate = None
        if len(recent) >= 2:
            try:
                newest = datetime.fromisoformat(
                    str(recent[0][0]).replace("Z", "+00:00")
                )
                oldest = datetime.fromisoformat(
                    str(recent[-1][0]).replace("Z", "+00:00")
                )
                elapsed = (newest - oldest).total_seconds()
                if elapsed > 0:
                    rate = sum(int(row[1] or 0) for row in recent[:-1]) / elapsed
            except (TypeError, ValueError):
                pass
        return {"status": "ok" if integrity == "ok" else "error",
                "integrity": integrity, "failed_recordings": failed,
                "recording_count": recording_count,
                "latest_recording_at": latest,
                "latest_recording_age_seconds": _timestamp_age(latest),
                "latest_processed_at": latest_processed,
                "latest_processed_age_seconds": _timestamp_age(latest_processed),
                "latest_detection_at": latest_detection,
                "latest_detection_age_seconds": _timestamp_age(latest_detection),
                "queue_depth": queue_depth,
                "recording_bytes_per_second": rate}
    except sqlite3.Error as error:
        return {"status": "error", "detail": str(error)}


def collect_health(config: FieldMouseConfig) -> dict[str, Any]:
    root = config.storage.recordings_directory
    root.mkdir(parents=True, exist_ok=True)
    disk = psutil.disk_usage(str(root))
    memory = psutil.virtual_memory()
    temperature = _temperature()
    database = _database(config.storage.database_path)
    service_checks = {name: _service(name) for name in config.health.services}
    cleanup = _cleanup_freshness()
    microphone = (
        {"status": "ok", "detail": config.audio.device}
        if shutil.which("arecord")
        else {"status": "unknown", "detail": "arecord unavailable"}
    )
    network = {"status": "ok" if psutil.net_if_stats() else "error",
               "interfaces": sum(1 for item in psutil.net_if_stats().values() if item.isup)}
    warnings = []
    advisories = []
    disk_state = storage_state(
        disk.percent,
        advisory=config.health.disk_advisory_percent,
        warning=config.health.disk_warning_percent,
        critical=config.health.disk_critical_percent,
        emergency=config.health.disk_emergency_percent,
    )
    if disk_state == "advisory":
        advisories.append("storage advisory")
    elif disk_state != "normal":
        warnings.append(f"storage {disk_state}")
    latest_age = database.get("latest_recording_age_seconds")
    if database.get("recording_count", 0) and (
        latest_age is None or latest_age > config.health.recording_stale_seconds
    ):
        warnings.append("recording stalled")
    processed_age = database.get("latest_processed_age_seconds")
    if database.get("recording_count", 0) and (
        processed_age is None or processed_age > config.health.birdnet_stale_seconds
    ):
        warnings.append("BirdNET processing stale")
    if temperature is not None and temperature >= config.health.temperature_warning_c:
        warnings.append("CPU temperature above threshold")
    if database["status"] != "ok":
        warnings.append("database unhealthy")
    if any(item["status"] == "error" for item in service_checks.values()):
        warnings.append("one or more services are not active")
    if cleanup["status"] == "error":
        warnings.append("cleanup failed")
    cleanup_age = cleanup.get("age_seconds")
    if cleanup_age is not None and cleanup_age > config.health.cleanup_stale_seconds:
        warnings.append("cleanup stale")
    return {
        "status": "degraded" if warnings else "ok",
        "station_id": config.station.id,
        "hostname": socket.gethostname(),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": round(time.time() - psutil.boot_time()),
        "cpu_percent": psutil.cpu_percent(interval=0.05),
        "memory": {"percent": memory.percent, "available_bytes": memory.available},
        "disk": {
            "percent": disk.percent,
            "free_bytes": disk.free,
            "state": disk_state,
            "forecast": storage_forecast(
                disk.free,
                database.get("recording_bytes_per_second"),
            ),
            "thresholds": {
                "advisory": config.health.disk_advisory_percent,
                "warning": config.health.disk_warning_percent,
                "critical": config.health.disk_critical_percent,
                "emergency": config.health.disk_emergency_percent,
            },
        },
        "temperature_c": temperature,
        "database": database,
        "microphone": microphone,
        "network": network,
        "services": service_checks,
        "cleanup": cleanup,
        "warnings": warnings,
        "advisories": advisories,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Field Mouse station health")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = collect_health(load_config(args.config))
    print(json.dumps(result, indent=2 if args.pretty else None))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
