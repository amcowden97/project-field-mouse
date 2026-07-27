(() => {
    "use strict";

    if (document.querySelector('[data-fm-device-link]')) {
        return;
    }

    const link = document.createElement("a");
    link.href = "/static/device/index.html";
    link.textContent = "Device";
    link.dataset.fmDeviceLink = "true";
    link.className = "fm-device-nav-link";

    const navigation =
        document.querySelector(".fm-navigation") ||
        document.querySelector("nav") ||
        document.querySelector(".fm-branding-bar");

    if (navigation) {
        navigation.appendChild(link);
    }
})();
