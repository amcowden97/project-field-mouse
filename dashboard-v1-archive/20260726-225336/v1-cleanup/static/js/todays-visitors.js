(() => {
    "use strict";

    const INITIAL_VISIBLE = 8;

    const ICON_RULES = [
        [/chickadee/i, "🐦"],
        [/towhee/i, "🐦"],
        [/finch/i, "🐤"],
        [/sparrow/i, "🐤"],
        [/wren/i, "🐦"],
        [/robin/i, "🐦"],
        [/jay/i, "🪶"],
        [/crow|raven/i, "🐦‍⬛"],
        [/dove|pigeon/i, "🕊️"],
        [/gull|tern/i, "🌊"],
        [/duck|teal|mallard|goose/i, "🦆"],
        [/hawk|eagle|falcon|osprey/i, "🦅"],
        [/owl/i, "🦉"],
        [/woodpecker|flicker/i, "🌳"],
        [/swallow|swift/i, "🪽"],
        [/heron|egret|crane/i, "🪶"],
        [/nighthawk/i, "🌙"]
    ];

    function chooseIcon(name) {
        for (const [pattern, icon] of ICON_RULES) {
            if (pattern.test(name)) {
                return icon;
            }
        }

        return "🐦";
    }

    function cleanText(value) {
        return String(value || "")
            .replace(/\s+/g, " ")
            .trim();
    }

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
                if (element.querySelector("audio")) {
                    results.add(element);
                }
            });
        }

        if (results.size === 0) {
            document.querySelectorAll(".card, article, li").forEach((element) => {
                if (element.querySelector("audio")) {
                    results.add(element);
                }
            });
        }

        return [...results];
    }

    function findName(card) {
        const preferredHeading =
            card.querySelector(".fm-species-title-content h2") ||
            card.querySelector(".fm-species-title-content h3") ||
            card.querySelector("h2") ||
            card.querySelector("h3") ||
            card.querySelector("strong");

        return cleanText(preferredHeading?.textContent);
    }

    function findConfidence(card) {
        const leafElements = [...card.querySelectorAll("*")]
            .filter((element) => element.children.length === 0);

        for (const element of leafElements) {
            const text = cleanText(element.textContent);
            const match = text.match(/^(\d{1,3}(?:\.\d+)?)%$/);

            if (match) {
                return Number(match[1]);
            }
        }

        const match = cleanText(card.textContent)
            .match(/(\d{1,3}(?:\.\d+)?)%/);

        return match ? Number(match[1]) : null;
    }

    function findDateText(card) {
        const candidates = [
            ...card.querySelectorAll("time"),
            ...card.querySelectorAll(
                ".date, .timestamp, .detection-time, .recorded-at"
            )
        ];

        for (const candidate of candidates) {
            const text = cleanText(candidate.textContent);
            if (text) {
                return text;
            }
        }

        const rawText = cleanText(card.textContent);

        const monthPattern =
            /\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+\d{4},?\s+\d{1,2}:\d{2}\s*(?:AM|PM)?\b/i;

        const monthMatch = rawText.match(monthPattern);
        if (monthMatch) {
            return monthMatch[0];
        }

        const isoPattern =
            /\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?/;

        const isoMatch = rawText.match(isoPattern);
        return isoMatch ? isoMatch[0] : "Recently";
    }

    function slugify(value) {
        return value
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/^-+|-+$/g, "");
    }

    function groupCards(cards) {
        const grouped = new Map();

        cards.forEach((card, index) => {
            const name = findName(card);

            if (!name) {
                return;
            }

            const confidence = findConfidence(card);
            const dateText = findDateText(card);

            if (!card.id) {
                card.id = `detection-${slugify(name)}-${index + 1}`;
            }

            if (!grouped.has(name)) {
                grouped.set(name, {
                    name,
                    count: 0,
                    maxConfidence: null,
                    latestText: dateText,
                    firstCard: card
                });
            }

            const entry = grouped.get(name);
            entry.count += 1;

            if (
                confidence !== null &&
                (
                    entry.maxConfidence === null ||
                    confidence > entry.maxConfidence
                )
            ) {
                entry.maxConfidence = confidence;
            }
        });

        return [...grouped.values()]
            .sort((a, b) => {
                if (b.count !== a.count) {
                    return b.count - a.count;
                }

                return a.name.localeCompare(b.name);
            });
    }

    function buildCard(visitor) {
        const anchor = document.createElement("a");
        anchor.className = "fm-visitor-card";
        anchor.href = `#${visitor.firstCard.id}`;

        const confidence =
            visitor.maxConfidence === null
                ? "—"
                : `${visitor.maxConfidence.toFixed(1)}%`;

        anchor.innerHTML = `
            <div class="fm-visitor-card__top">
                <span class="fm-visitor-card__icon"
                      aria-hidden="true">${chooseIcon(visitor.name)}</span>
                <span class="fm-visitor-card__count"
                      title="${visitor.count} detections">${visitor.count}×</span>
            </div>

            <h3 class="fm-visitor-card__name"></h3>
            <p class="fm-visitor-card__label">Visitor at Backyard Sanctuary</p>

            <div class="fm-visitor-card__details">
                <div class="fm-visitor-card__metric">
                    <span class="fm-visitor-card__metric-label">
                        Best confidence
                    </span>
                    <span class="fm-visitor-card__metric-value">
                        ${confidence}
                    </span>
                </div>

                <div class="fm-visitor-card__metric">
                    <span class="fm-visitor-card__metric-label">
                        Latest
                    </span>
                    <span class="fm-visitor-card__metric-value"></span>
                </div>
            </div>
        `;

        anchor.querySelector(".fm-visitor-card__name")
            .textContent = visitor.name;

        anchor.querySelector(
            ".fm-visitor-card__metric:last-child " +
            ".fm-visitor-card__metric-value"
        ).textContent = visitor.latestText;

        anchor.addEventListener("click", () => {
            window.setTimeout(() => {
                visitor.firstCard.classList.remove(
                    "fm-detection-highlight"
                );

                void visitor.firstCard.offsetWidth;

                visitor.firstCard.classList.add(
                    "fm-detection-highlight"
                );
            }, 150);
        });

        return anchor;
    }

    function findInsertionPoint() {
        const candidates = [
            document.querySelector(".fm-detection-list"),
            document.querySelector("#recent-activity"),
            document.querySelector(".recent-activity"),
            document.querySelector(
                ".detections, .detection-list, .recordings"
            )
        ].filter(Boolean);

        return candidates[0] || null;
    }

    function createVisitorsSection(visitors, cardCount) {
        const section = document.createElement("section");
        section.className = "fm-visitors";
        section.id = "todays-visitors";

        const visitorWord =
            visitors.length === 1 ? "species" : "species";

        section.innerHTML = `
            <div class="fm-visitors__heading">
                <div>
                    <p class="fm-visitors__eyebrow">
                        Field notes
                    </p>
                    <h2 class="fm-visitors__title">
                        Today’s Visitors
                    </h2>
                    <p class="fm-visitors__subtitle">
                        A quick look at who has stopped by the station.
                    </p>
                </div>

                <div class="fm-visitors__summary">
                    ${visitors.length} ${visitorWord} ·
                    ${cardCount} detections loaded
                </div>
            </div>

            <div class="fm-visitors__grid"></div>
        `;

        const grid = section.querySelector(".fm-visitors__grid");

        visitors.forEach((visitor, index) => {
            const card = buildCard(visitor);

            if (index >= INITIAL_VISIBLE) {
                card.hidden = true;
                card.dataset.fmExtraVisitor = "true";
            }

            grid.appendChild(card);
        });

        if (visitors.length > INITIAL_VISIBLE) {
            const controls = document.createElement("div");
            controls.className = "fm-visitors__more";

            const button = document.createElement("button");
            button.type = "button";
            button.className = "fm-visitors__toggle";
            button.textContent =
                `Show all ${visitors.length} visitors`;

            let expanded = false;

            button.addEventListener("click", () => {
                expanded = !expanded;

                section.querySelectorAll(
                    '[data-fm-extra-visitor="true"]'
                ).forEach((card) => {
                    card.hidden = !expanded;
                });

                button.textContent = expanded
                    ? "Show fewer visitors"
                    : `Show all ${visitors.length} visitors`;
            });

            controls.appendChild(button);
            section.appendChild(controls);
        }

        return section;
    }

    function render() {
        const cards = findDetectionCards();

        if (cards.length === 0) {
            return;
        }

        const visitors = groupCards(cards);
        if (visitors.length === 0) {
            return;
        }

        const existing = document.querySelector(".fm-visitors");
        const insertionPoint = findInsertionPoint();

        if (!insertionPoint) {
            return;
        }

        const section = createVisitorsSection(
            visitors,
            cards.length
        );

        if (existing) {
            existing.replaceWith(section);
        } else {
            insertionPoint.insertAdjacentElement(
                "beforebegin",
                section
            );
        }
    }

    function scheduleRender() {
        window.clearTimeout(window.__fmVisitorsTimer);

        window.__fmVisitorsTimer = window.setTimeout(
            render,
            140
        );
    }

    render();

    /*
     * Rebuild after the dashboard refreshes its detection feed.
     */
    const observer = new MutationObserver((mutations) => {
        const meaningfulChange = mutations.some((mutation) => {
            return [...mutation.addedNodes].some((node) => {
                return (
                    node.nodeType === Node.ELEMENT_NODE &&
                    !node.closest?.(".fm-visitors")
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
