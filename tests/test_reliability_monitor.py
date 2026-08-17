import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.system.reliability_monitor import assess_anomalies, record, summarize


def _sample(**overrides):
    sample = {
        "schema_version": 1,
        "recorded_at": datetime(2026, 8, 16, tzinfo=timezone.utc).isoformat(),
        "boot_id": "boot-a",
        "uptime_seconds": 3600,
        "load_average": [0.1, 0.2, 0.3],
        "cpu_percent": 5.0,
        "memory": {
            "total_bytes": 1024**3,
            "available_bytes": 512 * 1024**2,
            "used_percent": 50.0,
        },
        "swap": {
            "total_bytes": 1024**3,
            "used_bytes": 128 * 1024**2,
            "used_percent": 12.5,
            "sin_bytes": 0,
            "sout_bytes": 0,
        },
        "disk": {
            "total_bytes": 64 * 1024**3,
            "free_bytes": 16 * 1024**3,
            "used_percent": 75.0,
        },
        "disk_io": {},
        "network_io": {},
        "pi": {"temperature_c": 50.0, "throttled_flags": 0, "voltage": "volt=0.8V"},
        "services": {
            "fieldmouse-recorder.service": {
                "active_state": "active",
                "rss_bytes": 32 * 1024**2,
                "file_descriptors": 10,
                "restart_count": 0,
            }
        },
    }
    sample.update(overrides)
    return sample


def test_assess_anomalies_detects_pressure_and_growth() -> None:
    previous = _sample()
    current = _sample(
        memory={"available_bytes": 64 * 1024**2},
        swap={"used_bytes": 900 * 1024**2, "used_percent": 88.0},
        pi={"temperature_c": 81.0, "throttled_flags": 1},
    )

    reasons = assess_anomalies(current, previous)

    assert "memory_available_below_128_mib" in reasons
    assert "swap_usage_at_or_above_75_percent" in reasons
    assert "swap_growth_at_or_above_128_mib_per_interval" in reasons
    assert "cpu_temperature_at_or_above_80_c" in reasons
    assert "firmware_throttle_or_power_flag_set" in reasons


def test_record_appends_daily_metrics_and_preserves_latest_state(tmp_path: Path) -> None:
    sample = _sample()
    with patch("app.system.reliability_monitor.collect_sample", return_value=sample):
        recorded, reasons = record(tmp_path)

    metrics = tmp_path / "metrics-2026-08-16.jsonl"
    assert reasons == []
    assert json.loads(metrics.read_text().strip())["boot_id"] == "boot-a"
    assert json.loads((tmp_path / "latest.json").read_text()) == recorded
    assert not list(tmp_path.glob("diagnostic-*.json"))


def test_record_caps_diagnostic_snapshots(tmp_path: Path) -> None:
    for index in range(22):
        (tmp_path / f"diagnostic-20260801T00{index:02d}00Z.json").write_text("{}")
    sample = _sample(memory={"available_bytes": 64 * 1024**2})
    with (
        patch("app.system.reliability_monitor.collect_sample", return_value=sample),
        patch(
            "app.system.reliability_monitor._diagnostic_snapshot",
            return_value={"reasons": ["memory_available_below_128_mib"]},
        ),
    ):
        record(tmp_path)

    assert len(list(tmp_path.glob("diagnostic-*.json"))) == 20


def test_summarize_reports_resource_and_service_ranges(tmp_path: Path) -> None:
    first = _sample()
    second = _sample(
        recorded_at=datetime(2026, 8, 16, 0, 5, tzinfo=timezone.utc).isoformat(),
        swap={"used_bytes": 256 * 1024**2},
    )
    metrics = tmp_path / "metrics-2026-08-16.jsonl"
    metrics.write_text("\n".join(json.dumps(item) for item in (first, second)) + "\n")

    result = summarize(tmp_path)

    assert result["sample_count"] == 2
    assert result["swap_used_bytes"]["maximum"] == 256 * 1024**2
    assert result["services"]["fieldmouse-recorder.service"]["inactive_samples"] == 0
