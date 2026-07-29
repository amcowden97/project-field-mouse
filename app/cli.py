"""Unified Project Field Mouse command-line interface."""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import uuid
from pathlib import Path

from app.backups import create_backup, restore_backup, verify_backup
from app.config import DEFAULT_CONFIG_PATH, ConfigurationError, load_config
from app.migrations import migrate, migration_history
from app.simulator import MODES, simulate
from app.system.health_check import collect_health
from app.version import __version__

ROOT = Path(__file__).resolve().parents[1]


def _config_path(arguments: argparse.Namespace) -> Path:
    return Path(arguments.config or os.environ.get("PFM_CONFIG", DEFAULT_CONFIG_PATH)).resolve()


def _run_script(name: str) -> int:
    script = ROOT / "scripts" / f"{name}.sh"
    if platform.system() != "Linux":
        raise RuntimeError(f"pfm {name} requires Linux")
    return subprocess.run([str(script)], check=False).returncode


def _services() -> dict[str, str]:
    names = ("fieldmouse-recorder", "fieldmouse-birdnet", "fieldmouse-dashboard")
    if shutil.which("systemctl") is None:
        return {name: "systemd unavailable" for name in names}
    result = {}
    for name in names:
        process = subprocess.run(
            ["systemctl", "is-active", name], capture_output=True, text=True,
            timeout=3, check=False,
        )
        result[name] = (process.stdout or process.stderr).strip()
    return result


def _write_config(path: Path, name: str, station_id: str, timezone: str) -> None:
    if path.exists():
        raise RuntimeError(f"Refusing to overwrite existing configuration: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    station_uuid = str(uuid.uuid4())
    path.write_text(
        f'''[station]
id = "{station_id}"
uuid = "{station_uuid}"
name = "{name}"
timezone = "{timezone}"
location_name = ""
hardware_version = "{platform.machine() or 'unknown'}"
deployment_date = ""
capabilities = ["audio", "birdnet"]

[audio]
device = "default"
sample_rate = 48000
channels = 1
sample_format = "S16_LE"
recording_duration_seconds = 60
recording_interval_seconds = 900

[storage]
recordings_directory = "data/recordings"
database_path = "data/database/fieldmouse.db"
logs_directory = "logs"
backups_directory = "data/backups"

[detection]
enabled = true
minimum_confidence = 0.70

[birdnet]
enabled = true

[dashboard]
host = "0.0.0.0"
port = 8000
''',
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pfm", description="Operate Project Field Mouse")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", help="Station TOML path (or set PFM_CONFIG)")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("install", "update"):
        commands.add_parser(command)
    commands.add_parser("status")
    commands.add_parser("health").add_argument("--pretty", action="store_true")
    logs = commands.add_parser("logs")
    logs.add_argument("--service", default="fieldmouse")
    logs.add_argument("--lines", type=int, default=50)
    commands.add_parser("doctor")
    backup = commands.add_parser("backup")
    backup.add_argument("--output", type=Path)
    restore = commands.add_parser("restore")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--restore-config", action="store_true")
    verify = commands.add_parser("verify-backup")
    verify.add_argument("archive", type=Path)
    migrations = commands.add_parser("migrate")
    migrations.add_argument("--history", action="store_true")
    simulator = commands.add_parser("simulate")
    simulator.add_argument("--mode", choices=MODES, default="detections")
    simulator.add_argument("--count", type=int)
    simulator.add_argument("--seed", type=int, default=42)
    configuration = commands.add_parser("config")
    configuration.add_argument("action", choices=("show", "validate", "init"))
    configuration.add_argument("--name", default="Project Field Mouse")
    configuration.add_argument("--station-id", default=f"field-mouse-{socket.gethostname().lower()}")
    configuration.add_argument("--timezone", default="UTC")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command in {"install", "update"}:
            return _run_script(arguments.command)
        path = _config_path(arguments)
        if arguments.command == "config" and arguments.action == "init":
            _write_config(path, arguments.name, arguments.station_id, arguments.timezone)
            print(f"Created {path}")
            return 0
        config = load_config(path)
        if arguments.command == "status":
            print(json.dumps({"version": __version__, "station": config.station.id,
                              "services": _services()}, indent=2))
        elif arguments.command == "health":
            result = collect_health(config)
            print(json.dumps(result, indent=2 if arguments.pretty else None))
            return 0 if result["status"] == "ok" else 1
        elif arguments.command == "logs":
            log = config.storage.logs_directory / f"{arguments.service}.log"
            if not log.is_file():
                raise RuntimeError(f"Log not found: {log}")
            print("\n".join(log.read_text(encoding="utf-8").splitlines()[-arguments.lines:]))
        elif arguments.command == "doctor":
            checks = {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "raspberry_pi": Path("/proc/device-tree/model").exists(),
                "arecord": shutil.which("arecord") or "missing",
                "ffmpeg": shutil.which("ffmpeg") or "optional/missing",
                "config": str(path),
                "database_parent_writable": os.access(
                    config.storage.database_path.parent
                    if config.storage.database_path.parent.exists() else ROOT, os.W_OK
                ),
            }
            print(json.dumps(checks, indent=2))
            return 0 if checks["arecord"] != "missing" or platform.system() != "Linux" else 1
        elif arguments.command == "backup":
            migrate(config.storage.database_path, config.storage.backups_directory)
            archive = create_backup(config, path)
            if arguments.output:
                arguments.output.parent.mkdir(parents=True, exist_ok=True)
                archive.replace(arguments.output)
                archive = arguments.output
            print(f"Verified backup: {archive}")
        elif arguments.command == "verify-backup":
            print(json.dumps(verify_backup(arguments.archive), indent=2))
        elif arguments.command == "restore":
            restore_backup(
                arguments.archive, config.storage.database_path,
                path if arguments.restore_config else None,
            )
            print(f"Restored database from {arguments.archive}")
        elif arguments.command == "migrate":
            if arguments.history:
                for row in migration_history(config.storage.database_path):
                    print(f"{row[0]:04d} {row[1]} {row[3]}")
            else:
                applied = migrate(config.storage.database_path, config.storage.backups_directory)
                print("Database is current." if not applied else
                      "Applied: " + ", ".join(f"{item.version:04d}_{item.name}" for item in applied))
        elif arguments.command == "simulate":
            print(json.dumps(simulate(config, arguments.mode, arguments.count, arguments.seed), indent=2))
        elif arguments.command == "config":
            if arguments.action == "validate":
                print(f"Configuration is valid: {path}")
            else:
                print(json.dumps({
                    "path": str(path), "station": config.station.__dict__,
                    "database": str(config.storage.database_path),
                    "recordings": str(config.storage.recordings_directory),
                }, indent=2, default=str))
        return 0
    except (ConfigurationError, FileNotFoundError, RuntimeError, ValueError, OSError) as error:
        print(f"pfm: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
