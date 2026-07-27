(() => {
    "use strict";

    const elements = {
        overall: document.querySelector("#overall-status"),
        connection: document.querySelector("#connection-value"),
        connectionDetail: document.querySelector(
            "#connection-detail"
        ),
        hostname: document.querySelector("#hostname-value"),
        recorder: document.querySelector("#recorder-value"),
        recorderDetail: document.querySelector(
            "#recorder-detail"
        ),
        latest: document.querySelector("#latest-value"),
        latestDetail: document.querySelector(
            "#latest-detail"
        ),
        checked: document.querySelector("#checked-value"),
        responseTime: document.querySelector(
            "#response-time-value"
        ),
        raw: document.querySelector("#raw-health-data"),
        fieldTitle: document.querySelector(
            "#field-note-title"
        ),
        fieldText: document.querySelector("#field-note-text"),
        refresh: document.querySelector("#refresh-button")
    };

    function formatDate(value) {
        if (!value) {
            return {
                primary: "No recording",
                detail: "The station has not reported a recording time"
            };
        }

        const parsed = new Date(value);

        if (Number.isNaN(parsed.getTime())) {
            return {
                primary: String(value),
                detail: "Latest reported recording"
            };
        }

        return {
            primary: parsed.toLocaleTimeString([], {
                hour: "numeric",
                minute: "2-digit"
            }),
            detail: parsed.toLocaleDateString([], {
                weekday: "short",
                month: "short",
                day: "numeric",
                year: "numeric"
            })
        };
    }

    function setOverall(state, text) {
        elements.overall.className =
            `overall-status ${state}`;
        elements.overall.textContent = text;
    }

    async function loadHealth() {
        const started = performance.now();

        setOverall("checking", "Checking station…");
        elements.connection.textContent = "Checking…";
        elements.connectionDetail.textContent =
            "Contacting the health endpoint";

        try {
            const response = await fetch("/health", {
                cache: "no-store"
            });

            const elapsed = Math.round(
                performance.now() - started
            );

            if (!response.ok) {
                throw new Error(
                    `Health endpoint returned HTTP ${response.status}`
                );
            }

            const data = await response.json();
            const latest = formatDate(
                data.latest_recording_time ||
                data.latest_recording ||
                data.last_recording
            );

            const recorderRecent =
                data.recorder_recent === true;

            elements.connection.textContent = "Online";
            elements.connectionDetail.textContent =
                `Health endpoint responded in ${elapsed} ms`;

            elements.hostname.textContent =
                data.hostname || "Unknown station";

            elements.recorder.textContent =
                recorderRecent ? "Active" : "Needs attention";

            elements.recorderDetail.textContent =
                recorderRecent
                    ? "A recent recording was detected"
                    : "No recent recording was reported";

            elements.latest.textContent = latest.primary;
            elements.latestDetail.textContent = latest.detail;

            elements.checked.textContent =
                new Date().toLocaleTimeString();

            elements.responseTime.textContent =
                `${elapsed} ms`;

            elements.raw.textContent =
                JSON.stringify(data, null, 2);

            if (recorderRecent) {
                setOverall(
                    "healthy",
                    "Station healthy"
                );

                elements.fieldTitle.textContent =
                    "The station is listening";

                elements.fieldText.textContent =
                    "Backyard Sanctuary is online and has reported " +
                    "a recent recording. Field Mouse is quietly doing " +
                    "its job in the background.";
            } else {
                setOverall(
                    "unhealthy",
                    "Recorder may be stale"
                );

                elements.fieldTitle.textContent =
                    "The station is online, but quiet";

                elements.fieldText.textContent =
                    "The dashboard responded, but no recent recording " +
                    "was reported. The recorder service or microphone " +
                    "may need a quick check.";
            }
        } catch (error) {
            const elapsed = Math.round(
                performance.now() - started
            );

            setOverall("unhealthy", "Station unreachable");

            elements.connection.textContent = "Offline";
            elements.connectionDetail.textContent =
                error.message;

            elements.recorder.textContent = "Unknown";
            elements.recorderDetail.textContent =
                "Recorder status could not be checked";

            elements.checked.textContent =
                new Date().toLocaleTimeString();

            elements.responseTime.textContent =
                `${elapsed} ms`;

            elements.raw.textContent =
                String(error);

            elements.fieldTitle.textContent =
                "The station could not answer";

            elements.fieldText.textContent =
                "The dashboard could not reach the health endpoint. " +
                "The Pi may be restarting, disconnected, or the " +
                "dashboard service may be stopped.";
        }
    }

    elements.refresh.addEventListener("click", loadHealth);

    loadHealth();
    window.setInterval(loadHealth, 30000);
})();
