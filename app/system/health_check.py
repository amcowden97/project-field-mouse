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


def _temperature() -> float | None:
    thermal = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        return round(float(thermal.read_text().strip()) / 1000, 1)
    except (OSError, ValueError):
        temperatures = psutil.sensors_temperatures()
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
        connection.close()
        return {"status": "ok" if integrity == "ok" else "error",
                "integrity": integrity, "failed_recordings": failed,
                "latest_recording_at": latest}
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
    microphone = (
        {"status": "ok", "detail": config.audio.device}
        if shutil.which("arecord")
        else {"status": "unknown", "detail": "arecord unavailable"}
    )
    network = {"status": "ok" if psutil.net_if_stats() else "error",
               "interfaces": sum(1 for item in psutil.net_if_stats().values() if item.isup)}
    warnings = []
    if disk.percent >= config.health.disk_warning_percent:
        warnings.append("disk usage above threshold")
    if temperature is not None and temperature >= config.health.temperature_warning_c:
        warnings.append("CPU temperature above threshold")
    if database["status"] != "ok":
        warnings.append("database unhealthy")
    if any(item["status"] == "error" for item in service_checks.values()):
        warnings.append("one or more services are not active")
    return {
        "status": "degraded" if warnings else "ok",
        "station_id": config.station.id,
        "hostname": socket.gethostname(),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": round(time.time() - psutil.boot_time()),
        "cpu_percent": psutil.cpu_percent(interval=0.05),
        "memory": {"percent": memory.percent, "available_bytes": memory.available},
        "disk": {"percent": disk.percent, "free_bytes": disk.free},
        "temperature_c": temperature,
        "database": database,
        "microphone": microphone,
        "network": network,
        "services": service_checks,
        "warnings": warnings,
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
