"""Shared storage watermarks and recording-rate forecasting."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


STORAGE_STATES = ("normal", "advisory", "warning", "critical", "emergency")


def storage_state(
    used_percent: float,
    *,
    advisory: float = 80.0,
    warning: float = 90.0,
    critical: float = 95.0,
    emergency: float = 98.0,
) -> str:
    if used_percent >= emergency:
        return "emergency"
    if used_percent >= critical:
        return "critical"
    if used_percent >= warning:
        return "warning"
    if used_percent >= advisory:
        return "advisory"
    return "normal"


def storage_forecast(
    free_bytes: int,
    bytes_per_second: float | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not bytes_per_second or bytes_per_second <= 0:
        return {
            "bytes_per_day": None,
            "seconds_remaining": None,
            "estimated_full_at": None,
        }
    seconds = max(0, int(free_bytes / bytes_per_second))
    current = now or datetime.now(timezone.utc)
    return {
        "bytes_per_day": round(bytes_per_second * 86400),
        "seconds_remaining": seconds,
        "estimated_full_at": (current + timedelta(seconds=seconds)).isoformat(),
    }
