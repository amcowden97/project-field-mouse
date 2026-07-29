from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Callable

import psutil


@dataclass(frozen=True)
class PerformanceReport:
    iterations: int
    startup_seconds: float
    mean_latency_seconds: float
    min_latency_seconds: float
    max_latency_seconds: float
    process_cpu_seconds: float
    mean_cpu_percent: float
    peak_rss_bytes: int
    temperature_before_c: float | None
    temperature_after_c: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_cpu_temperature() -> float | None:
    thermal = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        return float(thermal.read_text(encoding="ascii").strip()) / 1000.0
    except (OSError, ValueError):
        return None


def profile_callable(
    operation: Callable[[], object],
    *,
    iterations: int = 10,
    startup_seconds: float = 0.0,
) -> PerformanceReport:
    if iterations < 1:
        raise ValueError("Iterations must be at least one.")
    process = psutil.Process(os.getpid())
    cpu_before = sum(process.cpu_times()[:2])
    temperature_before = read_cpu_temperature()
    latencies: list[float] = []
    cpu_samples: list[float] = []
    peak_rss = process.memory_info().rss
    process.cpu_percent(interval=None)
    for _ in range(iterations):
        started = time.perf_counter()
        operation()
        latencies.append(time.perf_counter() - started)
        cpu_samples.append(process.cpu_percent(interval=None))
        peak_rss = max(peak_rss, process.memory_info().rss)
    cpu_after = sum(process.cpu_times()[:2])
    return PerformanceReport(
        iterations,
        startup_seconds,
        mean(latencies),
        min(latencies),
        max(latencies),
        cpu_after - cpu_before,
        mean(cpu_samples),
        peak_rss,
        temperature_before,
        read_cpu_temperature(),
    )
