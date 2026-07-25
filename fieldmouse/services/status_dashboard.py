from __future__ import annotations

import argparse
import shutil
import sqlite3
import time
import tomllib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text


DEFAULT_CONFIG_PATH = Path("config/station.toml")


@dataclass(frozen=True)
class DashboardConfig:
    station_name: str
    timezone: str
    database_path: Path
    recordings_directory: Path
    refresh_seconds: float

    dawn_start: str
    dawn_end: str
    evening_start: str
    evening_end: str

    dawn_interval_seconds: int
    day_interval_seconds: int
    evening_interval_seconds: int
    night_interval_seconds: int

    burst_enabled: bool
    burst_interval_seconds: int
    burst_duration_minutes: int
    burst_minimum_confidence: float


def load_config(
    config_path: Path,
    refresh_seconds: float,
) -> DashboardConfig:
    with config_path.open("rb") as file:
        config = tomllib.load(file)

    station = config.get("station", {})
    storage = config.get("storage", {})
    adaptive = config.get("adaptive_recording", {})

    return DashboardConfig(
        station_name=str(
            station.get("name", "Project Field Mouse")
        ),
        timezone=str(
            station.get(
                "timezone",
                "America/Los_Angeles",
            )
        ),
        database_path=Path(
            storage.get(
                "database_path",
                "data/database/fieldmouse.db",
            )
        ),
        recordings_directory=Path(
            storage.get(
                "recordings_directory",
                "data/recordings",
            )
        ),
        refresh_seconds=refresh_seconds,
        dawn_start=str(
            adaptive.get("dawn_start", "05:00")
        ),
        dawn_end=str(
            adaptive.get("dawn_end", "09:00")
        ),
        evening_start=str(
            adaptive.get("evening_start", "17:00")
        ),
        evening_end=str(
            adaptive.get("evening_end", "21:00")
        ),
        dawn_interval_seconds=int(
            adaptive.get(
                "dawn_interval_seconds",
                120,
            )
        ),
        day_interval_seconds=int(
            adaptive.get(
                "day_interval_seconds",
                300,
            )
        ),
        evening_interval_seconds=int(
            adaptive.get(
                "evening_interval_seconds",
                300,
            )
        ),
        night_interval_seconds=int(
            adaptive.get(
                "night_interval_seconds",
                900,
            )
        ),
        burst_enabled=bool(
            adaptive.get("burst_enabled", True)
        ),
        burst_interval_seconds=int(
            adaptive.get(
                "burst_interval_seconds",
                60,
            )
        ),
        burst_duration_minutes=int(
            adaptive.get(
                "burst_duration_minutes",
                20,
            )
        ),
        burst_minimum_confidence=float(
            adaptive.get(
                "burst_minimum_confidence",
                0.50,
            )
        ),
    )


def open_database(
    database_path: Path,
) -> sqlite3.Connection | None:
    if not database_path.exists():
        return None

    connection = sqlite3.connect(
        f"file:{database_path}?mode=ro",
        uri=True,
        timeout=2,
    )

    connection.row_factory = sqlite3.Row
    return connection


def query_one(
    connection: sqlite3.Connection | None,
    sql: str,
    parameters: tuple = (),
) -> sqlite3.Row | None:
    if connection is None:
        return None

    try:
        return connection.execute(
            sql,
            parameters,
        ).fetchone()
    except sqlite3.Error:
        return None


def query_all(
    connection: sqlite3.Connection | None,
    sql: str,
    parameters: tuple = (),
) -> list[sqlite3.Row]:
    if connection is None:
        return []

    try:
        return connection.execute(
            sql,
            parameters,
        ).fetchall()
    except sqlite3.Error:
        return []


def parse_timestamp(
    value: object,
    timezone: ZoneInfo,
) -> datetime | None:
    if value is None:
        return None

    text = str(value).replace("Z", "+00:00")

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone)

    return parsed.astimezone(timezone)


def format_timestamp(
    value: object,
    timezone: ZoneInfo,
) -> str:
    parsed = parse_timestamp(value, timezone)

    if parsed is None:
        return "Unknown"

    return parsed.strftime("%-I:%M:%S %p")


def format_age(
    value: object,
    timezone: ZoneInfo,
) -> str:
    parsed = parse_timestamp(value, timezone)

    if parsed is None:
        return "unknown"

    seconds = max(
        int(
            (
                datetime.now(timezone) - parsed
            ).total_seconds()
        ),
        0,
    )

    if seconds < 60:
        return f"{seconds}s ago"

    if seconds < 3600:
        return f"{seconds // 60}m ago"

    if seconds < 86400:
        return f"{seconds // 3600}h ago"

    return f"{seconds // 86400}d ago"


def format_interval(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} seconds"

    minutes = seconds // 60

    if minutes == 1:
        return "1 minute"

    return f"{minutes} minutes"


def clock_minutes(value: str) -> int:
    hour, minute = value.split(":", maxsplit=1)
    return int(hour) * 60 + int(minute)


def latest_burst_detection(
    connection: sqlite3.Connection | None,
    config: DashboardConfig,
    timezone: ZoneInfo,
) -> datetime | None:
    if not config.burst_enabled:
        return None

    row = query_one(
        connection,
        """
        SELECT r.recorded_at
        FROM detections AS d
        JOIN recordings AS r
            ON r.id = d.recording_id
        WHERE d.confidence >= ?
        ORDER BY r.recorded_at DESC
        LIMIT 1
        """,
        (config.burst_minimum_confidence,),
    )

    if row is None:
        return None

    detected_at = parse_timestamp(
        row["recorded_at"],
        timezone,
    )

    if detected_at is None:
        return None

    burst_window = timedelta(
        minutes=config.burst_duration_minutes
    )

    if datetime.now(timezone) - detected_at <= burst_window:
        return detected_at

    return None


def current_mode(
    connection: sqlite3.Connection | None,
    config: DashboardConfig,
    timezone: ZoneInfo,
) -> tuple[str, int, str]:
    burst_detection = latest_burst_detection(
        connection,
        config,
        timezone,
    )

    if burst_detection is not None:
        return (
            "Bird activity burst",
            config.burst_interval_seconds,
            (
                "Triggered by a qualifying detection "
                f"{format_age(burst_detection, timezone)}"
            ),
        )

    now = datetime.now(timezone)
    now_minutes = now.hour * 60 + now.minute

    dawn_start = clock_minutes(config.dawn_start)
    dawn_end = clock_minutes(config.dawn_end)
    evening_start = clock_minutes(
        config.evening_start
    )
    evening_end = clock_minutes(config.evening_end)

    if dawn_start <= now_minutes < dawn_end:
        return (
            "Dawn",
            config.dawn_interval_seconds,
            "Higher-frequency morning monitoring",
        )

    if evening_start <= now_minutes < evening_end:
        return (
            "Evening",
            config.evening_interval_seconds,
            "Evening wildlife monitoring",
        )

    if dawn_end <= now_minutes < evening_start:
        return (
            "Day",
            config.day_interval_seconds,
            "Normal daytime schedule",
        )

    return (
        "Night",
        config.night_interval_seconds,
        "Reduced overnight schedule",
    )


def cpu_temperature() -> str:
    candidates = [
        Path(
            "/sys/class/thermal/thermal_zone0/temp"
        ),
        Path(
            "/sys/class/hwmon/hwmon0/temp1_input"
        ),
    ]

    for path in candidates:
        try:
            raw = float(path.read_text().strip())
            return f"{raw / 1000:.1f}°C"
        except (OSError, ValueError):
            continue

    return "Unavailable"


def memory_usage() -> tuple[float, float, float]:
    values: dict[str, int] = {}

    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", maxsplit=1)
            values[key] = int(value.strip().split()[0])
    except (OSError, ValueError):
        return 0.0, 0.0, 0.0

    total = values.get("MemTotal", 0) / 1024
    available = values.get("MemAvailable", 0) / 1024
    used = max(total - available, 0)

    percent = (used / total * 100) if total else 0

    return used, total, percent


def service_state(service_name: str) -> str:
    service_path = Path(
        "/run/systemd/system"
    )

    if not service_path.exists():
        return "unknown"

    try:
        import subprocess

        result = subprocess.run(
            [
                "systemctl",
                "is-active",
                service_name,
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )

        return result.stdout.strip() or "unknown"
    except (
        OSError,
        subprocess.SubprocessError,
    ):
        return "unknown"


def service_indicator(state: str) -> Text:
    if state == "active":
        return Text("● active", style="bold green")

    if state == "activating":
        return Text(
            "● starting",
            style="bold yellow",
        )

    return Text(
        f"● {state}",
        style="bold red",
    )


def build_header(
    config: DashboardConfig,
    timezone: ZoneInfo,
) -> Panel:
    now = datetime.now(timezone)

    title = Text()
    title.append("🐭  ", style="bold")
    title.append(
        "PROJECT FIELD MOUSE",
        style="bold cyan",
    )

    subtitle = Text()
    subtitle.append(
        config.station_name,
        style="bold white",
    )
    subtitle.append("   •   ")
    subtitle.append(
        now.strftime(
            "%A, %B %-d  %-I:%M:%S %p"
        ),
        style="dim",
    )

    return Panel(
        Align.center(Group(title, subtitle)),
        border_style="cyan",
    )


def build_service_panel() -> Panel:
    table = Table.grid(expand=True)
    table.add_column()
    table.add_column(justify="right")

    recorder = service_state(
        "fieldmouse-recorder.service"
    )
    birdnet = service_state(
        "fieldmouse-birdnet.service"
    )
    cleanup = service_state(
        "fieldmouse-cleanup.timer"
    )

    table.add_row(
        "Adaptive recorder",
        service_indicator(recorder),
    )
    table.add_row(
        "BirdNET worker",
        service_indicator(birdnet),
    )
    table.add_row(
        "Storage cleanup",
        service_indicator(cleanup),
    )

    return Panel(
        table,
        title="Station Services",
        border_style="green",
    )


def build_mode_panel(
    connection: sqlite3.Connection | None,
    config: DashboardConfig,
    timezone: ZoneInfo,
) -> Panel:
    mode, interval, reason = current_mode(
        connection,
        config,
        timezone,
    )

    table = Table.grid(expand=True)
    table.add_column(style="dim")
    table.add_column(justify="right")

    table.add_row(
        "Current mode",
        Text(mode, style="bold magenta"),
    )
    table.add_row(
        "Recording cadence",
        Text(
            f"Every {format_interval(interval)}",
            style="bold",
        ),
    )
    table.add_row(
        "Recording length",
        "60 seconds",
    )
    table.add_row(
        "Reason",
        reason,
    )

    return Panel(
        table,
        title="Adaptive Recording",
        border_style="magenta",
    )


def build_latest_recording_panel(
    connection: sqlite3.Connection | None,
    timezone: ZoneInfo,
) -> Panel:
    row = query_one(
        connection,
        """
        SELECT
            id,
            recorded_at,
            processing_status,
            file_path
        FROM recordings
        ORDER BY id DESC
        LIMIT 1
        """,
    )

    table = Table.grid(expand=True)
    table.add_column(style="dim")
    table.add_column(justify="right")

    if row is None:
        table.add_row(
            "Status",
            Text(
                "No recordings found",
                style="yellow",
            ),
        )
    else:
        status = str(
            row["processing_status"] or "unknown"
        )

        status_style = (
            "green"
            if status.lower()
            in {"complete", "completed", "processed"}
            else "yellow"
        )

        table.add_row(
            "Recording ID",
            str(row["id"]),
        )
        table.add_row(
            "Recorded",
            format_timestamp(
                row["recorded_at"],
                timezone,
            ),
        )
        table.add_row(
            "Age",
            format_age(
                row["recorded_at"],
                timezone,
            ),
        )
        table.add_row(
            "BirdNET status",
            Text(
                status,
                style=f"bold {status_style}",
            ),
        )

    return Panel(
        table,
        title="Latest Recording",
        border_style="blue",
    )


def build_daily_stats_panel(
    connection: sqlite3.Connection | None,
    timezone: ZoneInfo,
) -> Panel:
    now = datetime.now(timezone)
    day_start = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    ).isoformat()

    row = query_one(
        connection,
        """
        SELECT
            COUNT(DISTINCT r.id) AS recordings,
            COUNT(d.id) AS detections,
            COUNT(DISTINCT d.common_name) AS species
        FROM recordings AS r
        LEFT JOIN detections AS d
            ON d.recording_id = r.id
        WHERE r.recorded_at >= ?
        """,
        (day_start,),
    )

    total_row = query_one(
        connection,
        """
        SELECT
            COUNT(*) AS detections,
            COUNT(DISTINCT common_name) AS species
        FROM detections
        """,
    )

    table = Table.grid(expand=True)
    table.add_column(style="dim")
    table.add_column(justify="right")

    table.add_row(
        "Recordings today",
        str(row["recordings"] if row else 0),
    )
    table.add_row(
        "Detections today",
        str(row["detections"] if row else 0),
    )
    table.add_row(
        "Species today",
        str(row["species"] if row else 0),
    )
    table.add_row(
        "Lifetime detections",
        str(
            total_row["detections"]
            if total_row
            else 0
        ),
    )
    table.add_row(
        "Lifetime species",
        str(
            total_row["species"]
            if total_row
            else 0
        ),
    )

    return Panel(
        table,
        title="Wildlife Totals",
        border_style="yellow",
    )


def build_system_panel(
    config: DashboardConfig,
) -> Panel:
    disk = shutil.disk_usage(
        config.recordings_directory
        if config.recordings_directory.exists()
        else Path(".")
    )

    disk_percent = (
        disk.used / disk.total * 100
        if disk.total
        else 0
    )

    memory_used, memory_total, memory_percent = (
        memory_usage()
    )

    table = Table.grid(expand=True)
    table.add_column(style="dim")
    table.add_column(justify="right")

    table.add_row(
        "CPU temperature",
        cpu_temperature(),
    )
    table.add_row(
        "Memory",
        (
            f"{memory_used / 1024:.1f} / "
            f"{memory_total / 1024:.1f} GB"
        ),
    )
    table.add_row(
        "",
        ProgressBar(
            total=100,
            completed=memory_percent,
            width=22,
        ),
    )
    table.add_row(
        "Disk free",
        f"{disk.free / (1024 ** 3):.1f} GB",
    )
    table.add_row(
        "",
        ProgressBar(
            total=100,
            completed=disk_percent,
            width=22,
        ),
    )

    return Panel(
        table,
        title="Raspberry Pi Health",
        border_style="cyan",
    )


def build_detection_table(
    connection: sqlite3.Connection | None,
    timezone: ZoneInfo,
) -> Panel:
    rows = query_all(
        connection,
        """
        SELECT
            r.recorded_at,
            d.common_name,
            d.confidence
        FROM detections AS d
        JOIN recordings AS r
            ON r.id = d.recording_id
        ORDER BY d.id DESC
        LIMIT 15
        """,
    )

    table = Table(
        expand=True,
        show_header=True,
        header_style="bold cyan",
        row_styles=["", "dim"],
    )

    table.add_column(
        "Time",
        width=13,
        no_wrap=True,
    )
    table.add_column(
        "Bird",
        ratio=3,
    )
    table.add_column(
        "Confidence",
        justify="right",
        width=12,
    )
    table.add_column(
        "Age",
        justify="right",
        width=10,
    )

    if not rows:
        table.add_row(
            "—",
            "No birds detected yet",
            "—",
            "—",
        )
    else:
        for row in rows:
            confidence = float(
                row["confidence"] or 0
            )

            if confidence >= 0.80:
                style = "bold green"
            elif confidence >= 0.50:
                style = "yellow"
            else:
                style = "dim"

            table.add_row(
                format_timestamp(
                    row["recorded_at"],
                    timezone,
                ),
                str(
                    row["common_name"]
                    or "Unknown bird"
                ),
                Text(
                    f"{confidence * 100:.1f}%",
                    style=style,
                ),
                format_age(
                    row["recorded_at"],
                    timezone,
                ),
            )

    return Panel(
        table,
        title="Latest Bird Detections",
        subtitle="Newest first",
        border_style="green",
    )


def build_desktop_dashboard(
    config: DashboardConfig,
) -> Group:
    timezone = ZoneInfo(config.timezone)
    connection = open_database(
        config.database_path
    )

    try:
        top_grid = Table.grid(expand=True)
        top_grid.add_column(ratio=1)
        top_grid.add_column(ratio=1)
        top_grid.add_column(ratio=1)

        top_grid.add_row(
            build_service_panel(),
            build_mode_panel(
                connection,
                config,
                timezone,
            ),
            build_latest_recording_panel(
                connection,
                timezone,
            ),
        )

        middle_grid = Table.grid(expand=True)
        middle_grid.add_column(ratio=1)
        middle_grid.add_column(ratio=1)

        middle_grid.add_row(
            build_daily_stats_panel(
                connection,
                timezone,
            ),
            build_system_panel(config),
        )

        footer = Align.center(
            Text(
                (
                    "Refreshes every "
                    f"{config.refresh_seconds:g}s"
                    "  •  Press Ctrl+C to exit"
                ),
                style="dim",
            )
        )

        return Group(
            build_header(config, timezone),
            top_grid,
            middle_grid,
            build_detection_table(
                connection,
                timezone,
            ),
            footer,
        )
    finally:
        if connection is not None:
            connection.close()



def build_compact_dashboard(
    config: DashboardConfig,
) -> Group:
    """Build a phone-friendly dashboard that fits one terminal screen."""
    timezone = ZoneInfo(config.timezone)
    connection = open_database(config.database_path)

    try:
        now = datetime.now(timezone)
        mode, interval, reason = current_mode(
            connection,
            config,
            timezone,
        )

        latest = query_one(
            connection,
            """
            SELECT id, recorded_at, processing_status
            FROM recordings
            ORDER BY id DESC
            LIMIT 1
            """,
        )

        day_start = now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        ).isoformat()

        totals = query_one(
            connection,
            """
            SELECT
                COUNT(DISTINCT r.id) AS recordings,
                COUNT(d.id) AS detections,
                COUNT(DISTINCT d.common_name) AS species
            FROM recordings AS r
            LEFT JOIN detections AS d
                ON d.recording_id = r.id
            WHERE r.recorded_at >= ?
            """,
            (day_start,),
        )

        detections = query_all(
            connection,
            """
            SELECT
                r.recorded_at,
                d.common_name,
                d.confidence
            FROM detections AS d
            JOIN recordings AS r
                ON r.id = d.recording_id
            ORDER BY d.id DESC
            LIMIT 4
            """,
        )

        recorder = service_state(
            "fieldmouse-recorder.service"
        )
        birdnet = service_state(
            "fieldmouse-birdnet.service"
        )
        cleanup = service_state(
            "fieldmouse-cleanup.timer"
        )

        disk = shutil.disk_usage(
            config.recordings_directory
            if config.recordings_directory.exists()
            else Path(".")
        )

        memory_used, memory_total, memory_percent = (
            memory_usage()
        )

        heading = Text(justify="center")
        heading.append(
            "PROJECT FIELD MOUSE\n",
            style="bold cyan",
        )
        heading.append(
            config.station_name,
            style="bold white",
        )
        heading.append(
            f"  •  {now.strftime('%-I:%M:%S %p')}",
            style="dim",
        )

        status = Table.grid(expand=True)
        status.add_column()
        status.add_column(justify="right")

        status.add_row(
            "Mode",
            Text(mode, style="bold magenta"),
        )
        status.add_row(
            "Recording",
            f"Every {format_interval(interval)}",
        )
        status.add_row(
            "Recorder",
            service_indicator(recorder),
        )
        status.add_row(
            "BirdNET",
            service_indicator(birdnet),
        )
        status.add_row(
            "Cleanup",
            service_indicator(cleanup),
        )

        if latest is None:
            latest_text = "No recordings yet"
        else:
            latest_text = format_age(
                latest["recorded_at"],
                timezone,
            )

        status.add_row(
            "Latest audio",
            latest_text,
        )
        status.add_row(
            "Today",
            (
                f"{totals['species'] if totals else 0} species  •  "
                f"{totals['detections'] if totals else 0} detections"
            ),
        )
        status.add_row(
            "Pi health",
            (
                f"{cpu_temperature()}  •  "
                f"RAM {memory_percent:.0f}%  •  "
                f"{disk.free / (1024 ** 3):.1f} GB free"
            ),
        )

        birds = Table(
            expand=True,
            show_header=True,
            header_style="bold cyan",
            padding=(0, 1),
        )
        birds.add_column("Time", width=9, no_wrap=True)
        birds.add_column("Latest birds", ratio=1)
        birds.add_column(
            "Conf.",
            width=6,
            justify="right",
        )

        if not detections:
            birds.add_row(
                "—",
                "No birds detected yet",
                "—",
            )
        else:
            for row in detections:
                confidence = float(
                    row["confidence"] or 0
                )

                birds.add_row(
                    format_timestamp(
                        row["recorded_at"],
                        timezone,
                    ).replace(" ", "")[:-2],
                    str(
                        row["common_name"]
                        or "Unknown bird"
                    ),
                    f"{confidence * 100:.0f}%",
                )

        footer = Align.center(
            Text(
                (
                    f"Refresh {config.refresh_seconds:g}s"
                    "  •  Ctrl+C exits"
                ),
                style="dim",
            )
        )

        return Group(
            Panel(
                heading,
                border_style="cyan",
                padding=(0, 1),
            ),
            Panel(
                status,
                title="Station Status",
                border_style="green",
                padding=(0, 1),
            ),
            Panel(
                birds,
                border_style="yellow",
                padding=(0, 0),
            ),
            footer,
        )
    finally:
        if connection is not None:
            connection.close()


def resolve_layout(requested_layout: str) -> str:
    """Select compact mode for narrow or short terminals."""
    if requested_layout in {"compact", "desktop"}:
        return requested_layout

    terminal = shutil.get_terminal_size(
        fallback=(80, 24)
    )

    if terminal.columns < 85 or terminal.lines < 30:
        return "compact"

    return "desktop"


def build_dashboard(
    config: DashboardConfig,
    requested_layout: str = "auto",
) -> Group:
    layout = resolve_layout(requested_layout)

    if layout == "compact":
        return build_compact_dashboard(config)

    return build_desktop_dashboard(config)

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Display the live Project Field Mouse "
            "terminal dashboard."
        )
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to station.toml.",
    )

    parser.add_argument(
        "--refresh",
        type=float,
        default=5,
        help="Dashboard refresh interval in seconds.",
    )

    parser.add_argument(
        "--layout",
        choices=("auto", "compact", "desktop"),
        default="auto",
        help=(
            "Dashboard layout. Auto selects compact mode "
            "for narrow or short terminals."
        ),
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    if arguments.refresh <= 0:
        raise ValueError(
            "--refresh must be greater than zero."
        )

    config = load_config(
        arguments.config,
        arguments.refresh,
    )

    console = Console()

    try:
        with Live(
            build_dashboard(config, arguments.layout),
            console=console,
            screen=True,
            refresh_per_second=4,
        ) as live:
            while True:
                time.sleep(config.refresh_seconds)
                live.update(
                    build_dashboard(config, arguments.layout),
                    refresh=True,
                )
    except KeyboardInterrupt:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())