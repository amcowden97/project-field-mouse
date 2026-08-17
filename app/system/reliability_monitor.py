"""Low-overhead, persistent reliability telemetry for production stations."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psutil

SERVICES = (
    "fieldmouse-recorder.service",
    "fieldmouse-birdnet.service",
    "fieldmouse-dashboard.service",
)
MAINTENANCE_UNITS = (
    "fieldmouse-backup.service",
    "fieldmouse-cleanup.service",
    "fieldmouse-backup.timer",
    "fieldmouse-cleanup.timer",
)
STATE_FILE = "latest.json"
MIB = 1024 * 1024


def _command(arguments: list[str], timeout: float = 5) -> str | None:
    try:
        result = subprocess.run(
            arguments,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = result.stdout.strip()
    return output if result.returncode == 0 and output else None


def _integer(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _service_properties(unit: str) -> dict[str, Any]:
    output = _command(
        [
            "systemctl",
            "show",
            unit,
            "--no-pager",
            "--property=ActiveState,SubState,MainPID,NRestarts,TasksCurrent,CPUUsageNSec",
        ]
    )
    properties: dict[str, str] = {}
    for line in (output or "").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            properties[key] = value
    main_pid = _integer(properties.get("MainPID")) or 0
    processes = _process_tree(main_pid)
    return {
        "active_state": properties.get("ActiveState", "unknown"),
        "sub_state": properties.get("SubState", "unknown"),
        "main_pid": main_pid,
        "restart_count": _integer(properties.get("NRestarts")),
        "tasks": _integer(properties.get("TasksCurrent")),
        "cpu_time_ns": _integer(properties.get("CPUUsageNSec")),
        "processes": processes,
        "rss_bytes": sum(item["rss_bytes"] for item in processes),
        "swap_bytes": sum(item["swap_bytes"] for item in processes),
        "file_descriptors": sum(item["file_descriptors"] for item in processes),
        "threads": sum(item["threads"] for item in processes),
    }


def _maintenance_properties(unit: str) -> dict[str, Any]:
    output = _command(
        [
            "systemctl",
            "show",
            unit,
            "--no-pager",
            "--property=ActiveState,SubState,Result,ExecMainStatus,LastTriggerUSec,NextElapseUSecRealtime",
        ]
    )
    properties = {}
    for line in (output or "").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            properties[key] = value
    return {
        "active_state": properties.get("ActiveState", "unknown"),
        "sub_state": properties.get("SubState", "unknown"),
        "result": properties.get("Result") or None,
        "exit_status": _integer(properties.get("ExecMainStatus")),
        "last_trigger": properties.get("LastTriggerUSec") or None,
        "next_trigger": properties.get("NextElapseUSecRealtime") or None,
    }


def _proc_swap(pid: int) -> int:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmSwap:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0


def _process_tree(main_pid: int) -> list[dict[str, Any]]:
    if main_pid <= 0:
        return []
    try:
        root = psutil.Process(main_pid)
        processes = [root, *root.children(recursive=True)]
    except (psutil.Error, OSError):
        return []
    result = []
    for process in processes:
        try:
            memory = process.memory_info()
            result.append(
                {
                    "pid": process.pid,
                    "name": process.name(),
                    "rss_bytes": memory.rss,
                    "swap_bytes": _proc_swap(process.pid),
                    "file_descriptors": process.num_fds(),
                    "threads": process.num_threads(),
                }
            )
        except (psutil.Error, OSError):
            continue
    return result


def _pi_health() -> dict[str, Any]:
    throttled_raw = _command(["vcgencmd", "get_throttled"])
    temperature_raw = _command(["vcgencmd", "measure_temp"])
    voltage_raw = _command(["vcgencmd", "measure_volts", "core"])
    throttled = None
    if throttled_raw and "=" in throttled_raw:
        with contextlib.suppress(ValueError):
            throttled = int(throttled_raw.split("=", 1)[1], 16)
    temperature = None
    if temperature_raw and "=" in temperature_raw:
        with contextlib.suppress(ValueError):
            temperature = float(temperature_raw.split("=", 1)[1].rstrip("'C"))
    return {
        "temperature_c": temperature,
        "throttled_flags": throttled,
        "voltage": voltage_raw,
    }


def _storage_inventory() -> dict[str, Any]:
    state_root = Path("/var/lib/fieldmouse")
    recordings = state_root / "recordings"
    database = state_root / "database" / "fieldmouse.db"
    recording_count = 0
    recording_bytes = 0
    try:
        for path in recordings.rglob("*.wav"):
            try:
                recording_bytes += path.stat().st_size
                recording_count += 1
            except OSError:
                continue
    except OSError:
        pass

    def size(path: Path) -> int | None:
        try:
            return path.stat().st_size
        except OSError:
            return None

    log_bytes = 0
    try:
        for path in Path("/var/log/fieldmouse").rglob("*"):
            if path.is_file():
                log_bytes += size(path) or 0
    except OSError:
        pass
    return {
        "recording_count": recording_count,
        "recording_bytes": recording_bytes,
        "database_bytes": size(database),
        "database_wal_bytes": size(database.with_name(f"{database.name}-wal")),
        "database_shm_bytes": size(database.with_name(f"{database.name}-shm")),
        "fieldmouse_log_bytes": log_bytes,
    }


def _filesystem_health() -> dict[str, Any]:
    mount = _command(["findmnt", "--noheadings", "--output", "FSTYPE,OPTIONS", "/"])
    mount_options = mount.partition(" ")[2].split(",") if mount else []
    errors = {}
    for path in Path("/sys/fs/ext4").glob("*/errors_count"):
        try:
            errors[path.parent.name] = int(path.read_text().strip())
        except (OSError, ValueError):
            continue
    return {
        "root_mount": mount,
        "root_read_only": "ro" in mount_options,
        "ext4_error_counts": errors,
    }


def collect_sample() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    disk_io = psutil.disk_io_counters()
    network_io = psutil.net_io_counters()
    return {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "uptime_seconds": round(time.time() - psutil.boot_time()),
        "load_average": list(os.getloadavg()),
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory": {
            "total_bytes": memory.total,
            "available_bytes": memory.available,
            "used_percent": memory.percent,
        },
        "swap": {
            "total_bytes": swap.total,
            "used_bytes": swap.used,
            "used_percent": swap.percent,
            "sin_bytes": swap.sin,
            "sout_bytes": swap.sout,
        },
        "disk": {
            "total_bytes": disk.total,
            "free_bytes": disk.free,
            "used_percent": disk.percent,
        },
        "disk_io": None
        if disk_io is None
        else {
            "read_bytes": disk_io.read_bytes,
            "write_bytes": disk_io.write_bytes,
            "read_count": disk_io.read_count,
            "write_count": disk_io.write_count,
            "busy_time_ms": getattr(disk_io, "busy_time", None),
        },
        "network_io": {
            "bytes_sent": network_io.bytes_sent,
            "bytes_received": network_io.bytes_recv,
            "packets_sent": network_io.packets_sent,
            "packets_received": network_io.packets_recv,
            "errors_in": network_io.errin,
            "errors_out": network_io.errout,
            "drops_in": network_io.dropin,
            "drops_out": network_io.dropout,
        },
        "pi": _pi_health(),
        "services": {unit: _service_properties(unit) for unit in SERVICES},
        "maintenance": {unit: _maintenance_properties(unit) for unit in MAINTENANCE_UNITS},
        "storage_inventory": _storage_inventory(),
        "filesystem": _filesystem_health(),
    }


def assess_anomalies(sample: dict[str, Any], previous: dict[str, Any] | None) -> list[str]:
    reasons = []
    if sample["memory"]["available_bytes"] < 128 * MIB:
        reasons.append("memory_available_below_128_mib")
    if sample["swap"]["used_percent"] >= 75:
        reasons.append("swap_usage_at_or_above_75_percent")
    if sample["load_average"][1] >= max(4.0, (os.cpu_count() or 1) * 1.5):
        reasons.append("five_minute_load_high")
    if sample["disk"]["used_percent"] >= 90:
        reasons.append("root_disk_usage_at_or_above_90_percent")
    if (sample["pi"]["temperature_c"] or 0) >= 80:
        reasons.append("cpu_temperature_at_or_above_80_c")
    if sample["pi"]["throttled_flags"] not in (None, 0):
        reasons.append("firmware_throttle_or_power_flag_set")
    if sample.get("filesystem", {}).get("root_read_only"):
        reasons.append("root_filesystem_read_only")
    if any(sample.get("filesystem", {}).get("ext4_error_counts", {}).values()):
        reasons.append("ext4_error_count_nonzero")
    for unit, maintenance in sample.get("maintenance", {}).items():
        if maintenance.get("result") == "failed" or maintenance.get("exit_status") not in (
            None,
            0,
        ):
            reasons.append(f"{unit.removesuffix('.service')}_failed")
    for unit, service in sample["services"].items():
        label = unit.removesuffix(".service")
        if service["active_state"] != "active":
            reasons.append(f"{label}_not_active")
        if service["file_descriptors"] >= 1024:
            reasons.append(f"{label}_file_descriptors_at_or_above_1024")
    if previous and previous.get("boot_id") == sample.get("boot_id"):
        if sample["swap"]["used_bytes"] - previous["swap"]["used_bytes"] >= 128 * MIB:
            reasons.append("swap_growth_at_or_above_128_mib_per_interval")
        for unit, service in sample["services"].items():
            old = previous.get("services", {}).get(unit, {})
            label = unit.removesuffix(".service")
            if service["rss_bytes"] - old.get("rss_bytes", service["rss_bytes"]) >= 128 * MIB:
                reasons.append(f"{label}_rss_growth_at_or_above_128_mib_per_interval")
            if (
                service["file_descriptors"]
                - old.get("file_descriptors", service["file_descriptors"])
                >= 128
            ):
                reasons.append(f"{label}_file_descriptor_growth_at_or_above_128_per_interval")
            if (service["restart_count"] or 0) > (old.get("restart_count") or 0):
                reasons.append(f"{label}_restart_count_increased")
        old_network = previous.get("network_io", {})
        for counter in ("errors_in", "errors_out", "drops_in", "drops_out"):
            current_value = sample["network_io"].get(counter, 0)
            if current_value > old_network.get(counter, current_value):
                reasons.append(f"network_{counter}_increased")
        old_io = previous.get("disk_io") or {}
        current_io = sample.get("disk_io") or {}
        old_busy = old_io.get("busy_time_ms")
        current_busy = current_io.get("busy_time_ms")
        elapsed = (
            datetime.fromisoformat(sample["recorded_at"])
            - datetime.fromisoformat(previous["recorded_at"])
        ).total_seconds()
        if (
            old_busy is not None
            and current_busy is not None
            and elapsed > 0
            and (current_busy - old_busy) / (elapsed * 1000) >= 0.8
        ):
            reasons.append("disk_busy_at_or_above_80_percent_per_interval")
        old_free = previous["disk"]["free_bytes"]
        if old_free - sample["disk"]["free_bytes"] >= 1024 * MIB:
            reasons.append("root_disk_growth_at_or_above_1_gib_per_interval")
    return reasons


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _diagnostic_snapshot(sample: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    processes = []
    for process in psutil.process_iter(["pid", "ppid", "name", "memory_info", "num_threads"]):
        try:
            processes.append(
                {
                    "pid": process.info["pid"],
                    "ppid": process.info["ppid"],
                    "name": process.info["name"],
                    "rss_bytes": process.info["memory_info"].rss,
                    "threads": process.info["num_threads"],
                }
            )
        except (psutil.Error, AttributeError):
            continue
    processes.sort(key=lambda item: item["rss_bytes"], reverse=True)
    journals = {
        unit: _command(["journalctl", "--no-pager", "-n", "100", "-u", unit], timeout=10)
        for unit in SERVICES
    }
    return {
        "recorded_at": sample["recorded_at"],
        "reasons": reasons,
        "sample": sample,
        "top_processes": processes[:30],
        "kernel_warnings": _command(
            ["journalctl", "-k", "--no-pager", "-p", "warning..alert", "-n", "150"],
            timeout=10,
        ),
        "service_journals": journals,
    }


def _remove_expired(directory: Path, now: datetime, retention_days: int) -> None:
    cutoff = now - timedelta(days=retention_days)
    for path in directory.glob("metrics-*.jsonl"):
        try:
            if datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < cutoff:
                path.unlink()
        except OSError:
            continue
    snapshots = sorted(directory.glob("diagnostic-*.json"), key=lambda item: item.name)
    for path in snapshots[:-20]:
        try:
            path.unlink()
        except OSError:
            continue


def summarize(directory: Path) -> dict[str, Any]:
    samples = []
    for path in sorted(directory.glob("metrics-*.jsonl")):
        try:
            with path.open(encoding="utf-8") as stream:
                samples.extend(json.loads(line) for line in stream if line.strip())
        except (OSError, json.JSONDecodeError):
            continue
    if not samples:
        return {"sample_count": 0, "detail": "no reliability samples found"}
    services = {}
    for unit in SERVICES:
        values = [sample.get("services", {}).get(unit, {}) for sample in samples]
        rss = [value.get("rss_bytes", 0) for value in values]
        descriptors = [value.get("file_descriptors", 0) for value in values]
        restarts = [value.get("restart_count") for value in values]
        restarts = [value for value in restarts if value is not None]
        services[unit] = {
            "rss_bytes": {"first": rss[0], "last": rss[-1], "maximum": max(rss)},
            "file_descriptors": {
                "first": descriptors[0],
                "last": descriptors[-1],
                "maximum": max(descriptors),
            },
            "restart_count": {
                "first": restarts[0] if restarts else None,
                "last": restarts[-1] if restarts else None,
                "maximum": max(restarts) if restarts else None,
            },
            "inactive_samples": sum(value.get("active_state") != "active" for value in values),
        }
    return {
        "sample_count": len(samples),
        "first_recorded_at": samples[0]["recorded_at"],
        "last_recorded_at": samples[-1]["recorded_at"],
        "boot_ids": sorted({sample.get("boot_id") for sample in samples if sample.get("boot_id")}),
        "memory_available_bytes": {
            "first": samples[0]["memory"]["available_bytes"],
            "last": samples[-1]["memory"]["available_bytes"],
            "minimum": min(sample["memory"]["available_bytes"] for sample in samples),
        },
        "swap_used_bytes": {
            "first": samples[0]["swap"]["used_bytes"],
            "last": samples[-1]["swap"]["used_bytes"],
            "maximum": max(sample["swap"]["used_bytes"] for sample in samples),
        },
        "load_five_minute": {
            "maximum": max(sample["load_average"][1] for sample in samples),
        },
        "disk_used_percent": {
            "first": samples[0]["disk"]["used_percent"],
            "last": samples[-1]["disk"]["used_percent"],
            "maximum": max(sample["disk"]["used_percent"] for sample in samples),
        },
        "storage_inventory": {
            key: {
                "first": samples[0].get("storage_inventory", {}).get(key),
                "last": samples[-1].get("storage_inventory", {}).get(key),
            }
            for key in (
                "recording_count",
                "recording_bytes",
                "database_bytes",
                "database_wal_bytes",
                "fieldmouse_log_bytes",
            )
        },
        "filesystem": {
            "read_only_samples": sum(
                bool(sample.get("filesystem", {}).get("root_read_only")) for sample in samples
            ),
            "latest_ext4_error_counts": samples[-1]
            .get("filesystem", {})
            .get("ext4_error_counts", {}),
        },
        "temperature_c": {
            "maximum": max(
                (
                    sample["pi"]["temperature_c"]
                    for sample in samples
                    if sample["pi"]["temperature_c"] is not None
                ),
                default=None,
            ),
            "throttled_samples": sum(
                sample["pi"]["throttled_flags"] not in (None, 0) for sample in samples
            ),
        },
        "network_errors": {
            "last_in": samples[-1]["network_io"].get("errors_in"),
            "last_out": samples[-1]["network_io"].get("errors_out"),
            "last_drops_in": samples[-1]["network_io"].get("drops_in"),
            "last_drops_out": samples[-1]["network_io"].get("drops_out"),
        },
        "services": services,
        "diagnostic_snapshot_count": len(list(directory.glob("diagnostic-*.json"))),
    }


def record(output_directory: Path, retention_days: int = 30) -> tuple[dict[str, Any], list[str]]:
    output_directory.mkdir(parents=True, exist_ok=True, mode=0o750)
    previous = _read_json(output_directory / STATE_FILE)
    sample = collect_sample()
    reasons = assess_anomalies(sample, previous)
    now = datetime.fromisoformat(sample["recorded_at"])
    metrics = output_directory / f"metrics-{now:%Y-%m-%d}.jsonl"
    with metrics.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(sample, sort_keys=True) + "\n")
    metrics.chmod(0o640)
    _atomic_json(output_directory / STATE_FILE, sample)
    if reasons:
        stamp = now.strftime("%Y%m%dT%H%M%SZ")
        _atomic_json(
            output_directory / f"diagnostic-{stamp}.json",
            _diagnostic_snapshot(sample, reasons),
        )
    _remove_expired(output_directory, now, retention_days)
    return sample, reasons


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture Field Mouse reliability telemetry")
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("/var/log/fieldmouse/reliability"),
    )
    parser.add_argument("--retention-days", type=int, default=30)
    parser.add_argument(
        "--summarize",
        action="store_true",
        help="summarize existing samples without collecting a new sample",
    )
    arguments = parser.parse_args()
    if arguments.summarize:
        print(json.dumps(summarize(arguments.output_directory), indent=2, sort_keys=True))
        return 0
    sample, reasons = record(arguments.output_directory, arguments.retention_days)
    print(json.dumps({"recorded_at": sample["recorded_at"], "anomalies": reasons}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
