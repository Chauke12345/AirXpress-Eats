(function () {
    "use strict";

    const path = window.location.pathname.toLowerCase();

    const portals = [
        {
            id: "customer",
            match: p => p === "/" || p.startsWith("/customer/") || p.startsWith("/shop/"),
            name: "AirXpress Eats",
            description: "Faster access to your favourite food.",
            icon: "/static/orders/images/pwa/customer-icon-192.png",
            workerUrl: "/airxpress-sw.js",
            workerScope: "/"
        },
        {
            id: "driver",
            match: p => p.startsWith("/driver/"),
            name: "AirXpress Driver",
            description: "Quick access to your driver portal.",
            icon: "/static/orders/images/pwa/driver-icon-192.png",
            workerUrl: "/driver/driver-sw.js",
            workerScope: "/driver/"
        },
        {
            id: "merchant",
            match: p => p.startsWith("/merchant/") || p.startsWith("/staff/"),
            name: "AirXpress Merchant",
            description: "Quick access to your merchant portal.",
            icon: "/static/orders/images/pwa/merchant-icon-192.png",
            workerUrl: "/merchant/merchant-sw.js",
            workerScope: "/merchant/"
        },
        {
            id: "admin",
            match: p => p.startsWith("/owner/"),
            name: "AirXpress Admin",
            description: "Quick access to your administration portal.",
            icon: "/static/orders/images/pwa/admin-icon-192.png",
            workerUrl: "/owner/admin-sw.js",
            workerScope: "/owner/"
        }
    ];

    const portal = portals.find(item => item.match(path));
    if (!portal) return;

    const dismissalKey = "airxpressInstallDismissed-" + portal.id;

    function wasDismissed() {
        try {
            return localStorage.getItem(dismissalKey) === "yes";
        } catch (error) {
            return false;
        }
    }

    // Register the selected portal worker before installation checks.
    if (
        "serviceWorker" in navigator &&
        window.isSecureContext &&
        !(portal.id === "merchant" && path.startsWith("/staff/"))
    ) {
        navigator.serviceWorker.register(portal.workerUrl, {
            scope: portal.workerScope
        }).catch(error => {
            console.warn(
                "AirXpress " + portal.id + " service worker registration failed:",
                error
            );
        });
    }

    const isStandalone =
        window.matchMedia("(display-mode: standalone)").matches ||
        window.navigator.standalone === true;

    if (isStandalone) return;
    if (wasDismissed()) return;

    const isIOS =
        /iphone|ipad|ipod/i.test(navigator.userAgent) ||
        (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

    const markup = `
        <div id="airxpress-install-banner"
             role="dialog"
             aria-label="Install ${portal.name}"
             style="display:none;position:fixed;top:50%;left:50%;
             transform:translate(-50%,-50%);width:calc(100% - 32px);
             max-width:460px;background:#141414;color:#fff;
             border:1px solid #ff6800;border-radius:16px;padding:18px;
             z-index:999999;box-shadow:0 8px 30px rgba(0,0,0,.55);
             font-family:Arial,sans-serif;">

            <div style="display:flex;align-items:center;gap:12px;">
                <img src="${portal.icon}" alt="${portal.name}"
                     style="width:54px;height:54px;object-fit:contain;
                     border-radius:12px;background:#fff;">

                <div style="flex:1;">
                    <strong style="font-size:16px;">
                        Get ${portal.name} on your device
                    </strong>
                    <div style="font-size:13px;color:#ccc;margin-top:4px;">
                        ${portal.description}
                    </div>
                </div>

                <button id="airxpress-dismiss" type="button"
                    aria-label="Dismiss"
                    style="background:transparent;color:#fff;border:0;
                    font-size:24px;cursor:pointer;">&times;</button>
            </div>

            <div id="airxpress-install-help"
                 style="display:none;font-size:13px;color:#ddd;margin-top:14px;line-height:1.5;">
            </div>

            <div style="display:flex;gap:10px;margin-top:15px;">
                <button id="airxpress-install-button" type="button"
                    style="flex:1;background:#ff6800;color:#fff;border:0;
                    border-radius:9px;padding:12px;font-weight:700;
                    cursor:pointer;">How to install</button>

                <button id="airxpress-later" type="button"
                    style="background:#292929;color:#fff;border:0;
                    border-radius:9px;padding:12px 16px;cursor:pointer;">
                    Not now
                </button>
            </div>
        </div>`;

    document.body.insertAdjacentHTML("beforeend", markup);

    const banner = document.getElementById("airxpress-install-banner");
    const installButton = document.getElementById("airxpress-install-button");
    const dismissButton = document.getElementById("airxpress-dismiss");
    const laterButton = document.getElementById("airxpress-later");
    const installHelp = document.getElementById("airxpress-install-help");

    let installPrompt = null;
    let promptInProgress = false;

    function showBanner() {
        if (!wasDismissed()) {
            banner.style.display = "block";
        }
    }

    function dismissBanner() {
        banner.style.display = "none";
        try {
            localStorage.setItem(dismissalKey, "yes");
        } catch (error) {}
    }

    function showManualInstructions() {
        const ua = navigator.userAgent;
        let instructions;

        if (/EdgA|EdgiOS|Edg\//i.test(ua)) {
            instructions = "Open the browser menu and choose 'Install app' or 'Add to Home screen'.";
        } else if (/Chrome/i.test(ua) && /Android/i.test(ua)) {
            instructions = "Open Chrome's three-dot menu and choose 'Install app' or 'Add to Home screen'.";
        } else if (/Chrome/i.test(ua)) {
            instructions = "Use the install icon in Chrome's address bar, or open the three-dot menu and choose 'Cast, save and share' then 'Install page as app'.";
        } else {
            instructions = "Open your browser menu and look for 'Install app' or 'Add to Home screen'.";
        }

        installHelp.textContent = instructions;
        installHelp.style.display = "block";
        installButton.textContent = "How to install";
    }

    window.addEventListener("beforeinstallprompt", function (event) {
        event.preventDefault();
        installPrompt = event;
        installHelp.style.display = "none";
        installButton.textContent = "Install App";
        showBanner();
    });

    if (isIOS) {
        installButton.style.display = "none";
        installHelp.textContent =
            "To install this app, tap the Share button in Safari, then choose 'Add to Home Screen'.";
        installHelp.style.display = "block";
    }

    installButton.addEventListener("click", async function () {
        if (promptInProgress) return;

        if (!installPrompt) {
            showManualInstructions();
            return;
        }

        const promptEvent = installPrompt;
        installPrompt = null;
        promptInProgress = true;
        installButton.disabled = true;
        installButton.textContent = "Opening install prompt…";

        try {
            await promptEvent.prompt();
            const choice = await promptEvent.userChoice;

            if (choice && choice.outcome === "accepted") {
                banner.style.display = "none";
            } else {
                showManualInstructions();
            }
        } catch (error) {
            console.warn("AirXpress installation prompt failed:", error);
            showManualInstructions();
        } finally {
            promptInProgress = false;
            installButton.disabled = false;
        }
    });

    dismissButton.addEventListener("click", dismissBanner);
    laterButton.addEventListener("click", dismissBanner);

    window.addEventListener("appinstalled", function () {
        banner.style.display = "none";
        try {
            localStorage.removeItem(dismissalKey);
        } catch (error) {}
    });

    // Show the invitation, but only label the button "Install App" when
    // the browser has supplied a fresh native installation prompt.
    window.setTimeout(showBanner, 3000);
})();
