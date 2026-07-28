"use strict";

const formatBytes = (bytes) => {
    if (!bytes) return "0 B";

    const units = ["B", "KB", "MB", "GB", "TB"];
    let size = Number(bytes);
    let unit = 0;

    while (size >= 1024 && unit < units.length - 1) {
        size /= 1024;
        unit += 1;
    }

    return `${size.toFixed(1)} ${units[unit]}`;
};

const parseTimestamp = (value) => {
    if (!value) return null;

    let normalized = value;
    if (!/[zZ]|[+-]\d\d:\d\d$/.test(value)) {
        normalized = `${value}Z`;
    }

    const date = new Date(normalized);
    return Number.isNaN(date.getTime()) ? null : date;
};

const relativeTime = (value) => {
    const date = parseTimestamp(value);
    if (!date) return value || "unknown";

    const seconds = Math.round((date.getTime() - Date.now()) / 1000);
    const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

    if (Math.abs(seconds) < 60) return formatter.format(seconds, "second");

    const minutes = Math.round(seconds / 60);
    if (Math.abs(minutes) < 60) return formatter.format(minutes, "minute");

    const hours = Math.round(minutes / 60);
    if (Math.abs(hours) < 24) return formatter.format(hours, "hour");

    return formatter.format(Math.round(hours / 24), "day");
};

const renderTimes = () => {
    document.querySelectorAll(".local-time").forEach((element) => {
        const date = parseTimestamp(element.dataset.timestamp);
        if (date) {
            element.textContent = date.toLocaleString([], {
                dateStyle: "medium",
                timeStyle: "short",
            });
        }
    });

    document.querySelectorAll(".relative-time").forEach((element) => {
        element.textContent = relativeTime(element.dataset.timestamp);
    });
};

const setText = (id, value) => {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
};

const refreshDashboard = async () => {
    try {
        const response = await fetch("/api/dashboard", {
            headers: { Accept: "application/json" },
            cache: "no-store",
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        const stats = data.stats;

        setText("detections-24h", stats.detections_last_24_hours);
        setText("species-24h", stats.species_last_24_hours);
        setText("species-count", stats.species_count);
        setText("recording-count", stats.total_recordings);
        setText("recording-size", formatBytes(stats.total_recording_bytes));
        setText("disk-percent", stats.disk_percent);
        setText("disk-free", formatBytes(stats.disk_free));
        setText("last-refresh", "just refreshed");

        const diskBar = document.getElementById("disk-bar");
        if (diskBar) diskBar.style.width = `${stats.disk_percent}%`;

        const status = document.getElementById("station-status");
        const statusText = document.getElementById("station-status-text");

        if (status && statusText) {
            status.classList.toggle("offline", !stats.recorder_recent);
            statusText.textContent = stats.recorder_recent
                ? "Station listening"
                : "Recorder not recently seen";
        }
    } catch (error) {
        setText("last-refresh", "refresh unavailable");
        console.warn("Dashboard refresh failed:", error);
    }
};

renderTimes();
setInterval(renderTimes, 30_000);
setInterval(refreshDashboard, 5_000);

const renderCalendarDates = () => {
    document.querySelectorAll(".calendar-date").forEach((element) => {
        const value = element.dataset.date;
        if (!value) return;

        const date = new Date(`${value}T12:00:00`);

        if (!Number.isNaN(date.getTime())) {
            element.textContent = date.toLocaleDateString([], {
                month: "short",
                day: "numeric",
            });
        }
    });
};

renderCalendarDates();
