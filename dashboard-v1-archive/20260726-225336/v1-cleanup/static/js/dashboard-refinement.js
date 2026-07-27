(() => {
    "use strict";

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

    const NAV_ITEMS = [
        { label: "Overview", href: "/", icon: "🏡" },
        { label: "Life List", href: "/life-list", icon: "📖" },
        { label: "Species", href: "#recent-activity", icon: "🐦" },
        { label: "Device", href: "/static/device/index.html", icon: "⚙️" },
        { label: "Map", href: "/map", icon: "🗺️" }
    ];

    function speciesIcon(name) {
        for (const [pattern, icon] of ICON_RULES) {
            if (pattern.test(name)) {
                return icon;
            }
        }

        return "🐦";
    }

    function addNavigation() {
        if (document.querySelector(".fm-dashboard-nav")) {
            return;
        }

        const nav = document.createElement("nav");
        nav.className = "fm-dashboard-nav";
        nav.setAttribute("aria-label", "Project Field Mouse sections");

        const links = document.createElement("div");
        links.className = "fm-dashboard-nav__links";

        for (const item of NAV_ITEMS) {
            const anchor = document.createElement("a");
            anchor.href = item.href;
            anchor.textContent = `${item.icon} ${item.label}`;

            if (
                item.href === "/" &&
                (window.location.pathname === "/" ||
                 window.location.pathname === "")
            ) {
                anchor.setAttribute("aria-current", "page");
            }

            /*
             * Device and map pages may not exist yet.
             * Keep the navigation visible, but prevent a dead-end click.
             */
            if (
                (item.href === "/device" || item.href === "/map") &&
                window.location.pathname === "/"
            ) {
                anchor.addEventListener("click", (event) => {
                    event.preventDefault();

                    const existing = document.querySelector(".fm-nav-notice");
                    if (existing) {
                        existing.remove();
                    }

                    const notice = document.createElement("div");
                    notice.className = "fm-nav-notice";
                    notice.textContent =
                        `${item.label} is planned for an upcoming dashboard update.`;

                    Object.assign(notice.style, {
                        position: "fixed",
                        left: "50%",
                        bottom: "88px",
                        zIndex: "100",
                        transform: "translateX(-50%)",
                        padding: "10px 15px",
                        borderRadius: "999px",
                        color: "#fff",
                        background: "#2f5039",
                        boxShadow: "0 8px 24px rgba(39,55,45,.22)",
                        fontWeight: "700",
                        textAlign: "center"
                    });

                    document.body.appendChild(notice);
                    window.setTimeout(() => notice.remove(), 2600);
                });
            }

            links.appendChild(anchor);
        }

        const status = document.createElement("div");
        status.className = "fm-dashboard-nav__status";
        status.innerHTML = `
            <span class="fm-dashboard-nav__status-dot"
                  aria-hidden="true"></span>
            <span>Backyard Sanctuary online</span>
        `;

        nav.append(links, status);

        const banner = document.querySelector(".fm-visual-banner");

        if (banner) {
            banner.insertAdjacentElement("afterend", nav);
        } else {
            document.body.prepend(nav);
        }
    }

    function findDetectionCards() {
        const directSelectors = [
            ".detection-card",
            ".detection",
            ".recording-card",
            ".activity-card",
            ".recent-detection",
            '[class*="detection-card"]',
            '[class*="recording-card"]'
        ];

        const found = new Set();

        for (const selector of directSelectors) {
            document.querySelectorAll(selector).forEach((element) => {
                if (element.querySelector("audio")) {
                    found.add(element);
                }
            });
        }

        /*
         * Fallback for templates where cards only have a generic "card" class.
         */
        if (found.size === 0) {
            document.querySelectorAll(".card, article, li").forEach((element) => {
                if (element.querySelector("audio")) {
                    found.add(element);
                }
            });
        }

        return [...found];
    }

    function findSpeciesHeading(card) {
        return (
            card.querySelector("h2") ||
            card.querySelector("h3") ||
            card.querySelector("strong") ||
            card.querySelector("a")
        );
    }

    function decorateDetectionCard(card) {
        if (card.dataset.fmRefined === "true") {
            return;
        }

        const heading = findSpeciesHeading(card);
        if (!heading) {
            return;
        }

        const speciesName = heading.textContent.trim();
        if (!speciesName) {
            return;
        }

        card.dataset.fmRefined = "true";

        const titleRow = document.createElement("div");
        titleRow.className = "fm-species-title-row";

        const icon = document.createElement("span");
        icon.className = "fm-species-icon";
        icon.textContent = speciesIcon(speciesName);
        icon.setAttribute("aria-hidden", "true");

        const titleContent = document.createElement("div");
        titleContent.className = "fm-species-title-content";

        const originalParent = heading.parentElement;

        /*
         * Move the heading and an immediately-following scientific name
         * into the new title group when possible.
         */
        titleContent.appendChild(heading);

        if (originalParent) {
            const possibleScientificName = [...originalParent.children].find(
                (child) =>
                    child !== titleRow &&
                    child !== heading &&
                    (
                        child.tagName === "EM" ||
                        child.tagName === "I" ||
                        child.classList.contains("scientific-name")
                    )
            );

            if (possibleScientificName) {
                titleContent.appendChild(possibleScientificName);
            }
        }

        titleRow.append(icon, titleContent);
        card.prepend(titleRow);

        const confidenceText = [...card.querySelectorAll("*")]
            .map((element) => ({
                element,
                text: element.textContent.trim()
            }))
            .find(
                ({ element, text }) =>
                    element.children.length === 0 &&
                    /^\d{1,3}(?:\.\d+)?%$/.test(text)
            );

        if (confidenceText) {
            confidenceText.element.classList.add("fm-confidence-pill");
        }
    }

    function markDetectionList(cards) {
        if (cards.length === 0) {
            return;
        }

        const counts = new Map();

        for (const card of cards) {
            const parent = card.parentElement;
            if (!parent) {
                continue;
            }

            counts.set(parent, (counts.get(parent) || 0) + 1);
        }

        const bestParent = [...counts.entries()]
            .sort((a, b) => b[1] - a[1])[0]?.[0];

        if (bestParent) {
            bestParent.classList.add("fm-detection-list");
            bestParent.id ||= "recent-activity";
        }
    }

    function removeDuplicateGenericIcons(cards) {
        for (const card of cards) {
            const titleRow = card.querySelector(".fm-species-title-row");
            if (!titleRow) {
                continue;
            }

            for (const node of card.childNodes) {
                if (
                    node.nodeType === Node.TEXT_NODE &&
                    node.textContent.trim() === "🐦"
                ) {
                    node.textContent = "";
                }
            }

            card.querySelectorAll("span").forEach((span) => {
                if (
                    !span.classList.contains("fm-species-icon") &&
                    span.textContent.trim() === "🐦"
                ) {
                    span.hidden = true;
                }
            });
        }
    }

    function refineDashboard() {
        addNavigation();

        const cards = findDetectionCards();

        cards.forEach(decorateDetectionCard);
        markDetectionList(cards);
        removeDuplicateGenericIcons(cards);
    }

    refineDashboard();

    /*
     * The current dashboard can refresh asynchronously.
     * Watch for newly-rendered detection cards and decorate them too.
     */
    const observer = new MutationObserver(() => {
        window.clearTimeout(window.__fmRefineTimer);

        window.__fmRefineTimer = window.setTimeout(
            refineDashboard,
            80
        );
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
})();
