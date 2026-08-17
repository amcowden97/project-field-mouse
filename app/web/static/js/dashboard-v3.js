"use strict";

const parseTimestamp = (value) => {
    if (!value) return null;

    const normalized = /[zZ]|[+-]\d\d:\d\d$/.test(value)
        ? value
        : `${value}Z`;
    const date = new Date(normalized);

    return Number.isNaN(date.getTime()) ? null : date;
};

const formatRelativeTime = (value) => {
    const date = parseTimestamp(value);
    if (!date) return value || "Unknown";

    const seconds = Math.round((date.getTime() - Date.now()) / 1000);
    const formatter = new Intl.RelativeTimeFormat(undefined, {
        numeric: "auto",
    });

    if (Math.abs(seconds) < 60) {
        return formatter.format(seconds, "second");
    }

    const minutes = Math.round(seconds / 60);
    if (Math.abs(minutes) < 60) {
        return formatter.format(minutes, "minute");
    }

    const hours = Math.round(minutes / 60);
    if (Math.abs(hours) < 24) {
        return formatter.format(hours, "hour");
    }

    const days = Math.round(hours / 24);
    if (Math.abs(days) < 30) {
        return formatter.format(days, "day");
    }

    return date.toLocaleDateString([], {
        dateStyle: "medium",
    });
};

const renderTimes = (root = document) => {
    root.querySelectorAll(".local-time").forEach((element) => {
        const date = parseTimestamp(element.dataset.timestamp);
        if (!date) return;

        element.textContent = date.toLocaleString([], {
            dateStyle: "medium",
            timeStyle: "short",
        });
    });

    root.querySelectorAll(".relative-time").forEach((element) => {
        element.textContent = formatRelativeTime(
            element.dataset.timestamp,
        );
    });

    root.querySelectorAll(".calendar-date").forEach((element) => {
        const value = element.dataset.date;
        if (!value) return;

        const date = new Date(`${value}T12:00:00`);
        if (Number.isNaN(date.getTime())) return;

        element.textContent = date.toLocaleDateString([], {
            month: "short",
            day: "numeric",
        });
    });
};

const clampPercent = (value) => (
    Math.min(100, Math.max(0, Number(value) || 0))
);

const renderMeters = (root = document) => {
    root.querySelectorAll("[data-meter-value]").forEach((element) => {
        element.style.width = `${clampPercent(
            element.dataset.meterValue,
        )}%`;
    });
};

const renderChart = (chart) => {
    const bars = Array.from(
        chart.querySelectorAll("[data-chart-value]"),
    );
    const maximum = Math.max(
        1,
        ...bars.map((bar) => Number(bar.dataset.chartValue) || 0),
    );

    bars.forEach((bar) => {
        const value = Number(bar.dataset.chartValue) || 0;
        const percent = value > 0
            ? Math.max(4, (value / maximum) * 100)
            : 2;

        bar.style.height = `${percent}%`;
    });
};

const renderCharts = (root = document) => {
    root.querySelectorAll(
        ".pfm-timeline, .pfm-history-chart, .pfm-week-chart",
    ).forEach(renderChart);
};

const initializeInfiniteActivity = () => {
    const list = document.querySelector("[data-activity-list]");
    const loadMore = document.querySelector("[data-load-more]");
    const status = document.querySelector("[data-load-status]");
    const sentinel = document.querySelector("[data-load-sentinel]");

    if (!list || !loadMore) return;

    let loading = false;
    let observer = null;

    const setStatus = (message) => {
        if (status) status.textContent = message;
    };

    const finish = () => {
        loadMore.remove();
        if (sentinel) sentinel.remove();
        setStatus("You have reached the end of the listening log.");
        if (observer) observer.disconnect();
    };

    const loadNextPage = async (event) => {
        if (event) event.preventDefault();
        if (loading || !loadMore.href) return;

        loading = true;
        loadMore.setAttribute("aria-disabled", "true");
        setStatus("Loading more observations…");

        try {
            const response = await fetch(loadMore.href, {
                headers: {
                    Accept: "text/html",
                },
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const html = await response.text();
            const parsed = new DOMParser().parseFromString(
                html,
                "text/html",
            );
            const nextList = parsed.querySelector(
                "[data-activity-list]",
            );

            if (!nextList) {
                throw new Error("Activity list missing from response");
            }

            const items = Array.from(
                nextList.querySelectorAll(".pfm-detection"),
            );

            items.forEach((item) => list.append(item));
            renderTimes(list);
            renderMeters(list);

            const nextButton = parsed.querySelector("[data-load-more]");
            if (nextButton && nextButton.href) {
                loadMore.href = nextButton.href;
                loadMore.removeAttribute("aria-disabled");
                setStatus(
                    `${items.length} more observations added.`,
                );
            } else {
                finish();
            }
        } catch (error) {
            loadMore.removeAttribute("aria-disabled");
            setStatus(
                "More observations could not be loaded. Use the button to try again.",
            );
            console.warn("Activity loading failed:", error);
        } finally {
            loading = false;
        }
    };

    loadMore.addEventListener("click", loadNextPage);

    if ("IntersectionObserver" in window && sentinel) {
        observer = new IntersectionObserver(
            (entries) => {
                if (entries.some((entry) => entry.isIntersecting)) {
                    loadNextPage();
                }
            },
            {
                rootMargin: "240px 0px",
            },
        );
        observer.observe(sentinel);
    }
};

const initializeDashboard = () => {
    renderTimes();
    renderMeters();
    renderCharts();
    initializeInfiniteActivity();

    window.setInterval(() => renderTimes(), 30_000);
};

if (document.readyState === "loading") {
    document.addEventListener(
        "DOMContentLoaded",
        initializeDashboard,
        { once: true },
    );
} else {
    initializeDashboard();
}
