(() => {
    "use strict";

    if (document.querySelector(".fm-visual-banner")) {
        return;
    }

    const banner = document.createElement("div");
    banner.className = "fm-visual-banner";
    banner.innerHTML = `
        <div class="fm-brand">
            <span class="fm-brand-mouse" aria-hidden="true"></span>
            <span>Project Field Mouse</span>
        </div>
        <span class="fm-station-label">BACKYARD SANCTUARY · LIVE FIELD STATION</span>
    `;

    document.body.prepend(banner);

    const meadow = document.createElement("div");
    meadow.className = "fm-meadow";
    meadow.setAttribute("aria-hidden", "true");
    meadow.innerHTML = `
        <span class="fm-bird">🐦</span>
        <span class="fm-log"></span>
        <span class="fm-meadow-mouse"></span>
    `;
    document.body.appendChild(meadow);

    [
        ["fm-leaf fm-leaf-one", "❧"],
        ["fm-leaf fm-leaf-two", "❧"],
        ["fm-leaf fm-leaf-three", "❧"]
    ].forEach(([className, symbol]) => {
        const leaf = document.createElement("span");
        leaf.className = className;
        leaf.textContent = symbol;
        leaf.setAttribute("aria-hidden", "true");
        document.body.appendChild(leaf);
    });

    document.querySelectorAll(
        ".card, .stat-card, .panel, .status-card, .detection-card, .metric-card"
    ).forEach((card, index) => {
        card.style.animationDelay = `${Math.min(index * 45, 360)}ms`;
    });
})();
