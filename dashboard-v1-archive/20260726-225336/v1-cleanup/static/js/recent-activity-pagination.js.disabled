(() => {
    "use strict";

    const INITIAL_COUNT = 12;
    const PAGE_SIZE = 12;

    let visibleCount = INITIAL_COUNT;
    let lastKnownTotal = 0;

    function findDetectionCards() {
        const selectors = [
            ".detection-card",
            ".detection",
            ".recording-card",
            ".activity-card",
            ".recent-detection",
            '[class*="detection-card"]',
            '[class*="recording-card"]'
        ];

        const results = new Set();

        for (const selector of selectors) {
            document.querySelectorAll(selector).forEach((element) => {
                if (
                    element.querySelector("audio") &&
                    !element.closest(".fm-visitors")
                ) {
                    results.add(element);
                }
            });
        }

        if (results.size === 0) {
            document.querySelectorAll(".card, article, li").forEach((element) => {
                if (
                    element.querySelector("audio") &&
                    !element.closest(".fm-visitors")
                ) {
                    results.add(element);
                }
            });
        }

        return [...results];
    }

    function findList(cards) {
        if (cards.length === 0) {
            return null;
        }

        const parentCounts = new Map();

        for (const card of cards) {
            const parent = card.parentElement;

            if (!parent) {
                continue;
            }

            parentCounts.set(
                parent,
                (parentCounts.get(parent) || 0) + 1
            );
        }

        return [...parentCounts.entries()]
            .sort((a, b) => b[1] - a[1])[0]?.[0] || null;
    }

    function createControls(list) {
        let controls = document.querySelector(
            ".fm-activity-pagination"
        );

        if (controls) {
            return controls;
        }

        controls = document.createElement("div");
        controls.className = "fm-activity-pagination";

        controls.innerHTML = `
            <div class="fm-activity-pagination__status"
                 aria-live="polite"></div>

            <div class="fm-activity-pagination__actions">
                <button
                    type="button"
                    class="
                        fm-activity-pagination__button
                        fm-activity-pagination__button--secondary
                        fm-activity-pagination__fewer
                    "
                    hidden
                >
                    Show fewer
                </button>

                <button
                    type="button"
                    class="
                        fm-activity-pagination__button
                        fm-activity-pagination__more
                    "
                >
                    Load more
                </button>
            </div>
        `;

        list.insertAdjacentElement("afterend", controls);

        controls
            .querySelector(".fm-activity-pagination__more")
            .addEventListener("click", () => {
                visibleCount += PAGE_SIZE;
                render();
            });

        controls
            .querySelector(".fm-activity-pagination__fewer")
            .addEventListener("click", () => {
                visibleCount = INITIAL_COUNT;
                render();

                const activityHeading =
                    document.querySelector("#recent-activity") ||
                    list;

                activityHeading.scrollIntoView({
                    behavior: "smooth",
                    block: "start"
                });
            });

        return controls;
    }

    function updateControls(controls, total) {
        const shown = Math.min(visibleCount, total);

        const status = controls.querySelector(
            ".fm-activity-pagination__status"
        );

        const moreButton = controls.querySelector(
            ".fm-activity-pagination__more"
        );

        const fewerButton = controls.querySelector(
            ".fm-activity-pagination__fewer"
        );

        status.innerHTML = `
            Showing <strong>${shown}</strong>
            of <strong>${total}</strong> recent detections
        `;

        if (shown >= total) {
            moreButton.hidden = true;
        } else {
            const nextCount = Math.min(PAGE_SIZE, total - shown);

            moreButton.hidden = false;
            moreButton.textContent =
                `Load ${nextCount} more`;
        }

        fewerButton.hidden =
            visibleCount <= INITIAL_COUNT ||
            total <= INITIAL_COUNT;

        if (total === 0) {
            controls.hidden = true;
        } else {
            controls.hidden = false;
        }
    }

    function render() {
        const cards = findDetectionCards();
        const total = cards.length;

        if (total === 0) {
            return;
        }

        /*
         * If the dashboard refresh adds new detections, keep the
         * current expanded state rather than collapsing unexpectedly.
         */
        if (
            lastKnownTotal > 0 &&
            total < lastKnownTotal &&
            visibleCount > total
        ) {
            visibleCount = Math.max(
                INITIAL_COUNT,
                total
            );
        }

        lastKnownTotal = total;

        cards.forEach((card, index) => {
            const shouldHide = index >= visibleCount;

            card.classList.toggle(
                "fm-activity-hidden",
                shouldHide
            );

            card.setAttribute(
                "aria-hidden",
                shouldHide ? "true" : "false"
            );
        });

        const list = findList(cards);
        if (!list) {
            return;
        }

        const controls = createControls(list);
        updateControls(controls, total);
    }

    function scheduleRender() {
        window.clearTimeout(
            window.__fmActivityPaginationTimer
        );

        window.__fmActivityPaginationTimer =
            window.setTimeout(render, 160);
    }

    render();

    /*
     * The current dashboard may replace its activity cards
     * during automatic refreshes.
     */
    const observer = new MutationObserver((mutations) => {
        const meaningfulChange = mutations.some((mutation) => {
            return [...mutation.addedNodes].some((node) => {
                if (node.nodeType !== Node.ELEMENT_NODE) {
                    return false;
                }

                if (
                    node.classList?.contains(
                        "fm-activity-pagination"
                    )
                ) {
                    return false;
                }

                return !node.closest?.(
                    ".fm-activity-pagination"
                );
            });
        });

        if (meaningfulChange) {
            scheduleRender();
        }
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
})();
