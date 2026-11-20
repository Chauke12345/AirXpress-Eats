(function () {
    "use strict";

    const path = window.location.pathname.toLowerCase();

    const portals = [
        {
            id: "customer",
            match: p => p === "/" || p.startsWith("/customer/") || p.startsWith("/shop/"),
            name: "AirXpress Eats",
            description: "Faster access to your favourite food.",
            icon: "/static/orders/images/pwa/customer-icon-192.png"
        },
        {
            id: "driver",
            match: p => p.startsWith("/driver/"),
            name: "AirXpress Driver",
            description: "Quick access to your driver portal.",
            icon: "/static/orders/images/pwa/driver-icon-192.png"
        },
        {
            id: "merchant",
            match: p => p.startsWith("/merchant/") || p.startsWith("/staff/"),
            name: "AirXpress Merchant",
            description: "Quick access to your merchant portal.",
            icon: "/static/orders/images/pwa/merchant-icon-192.png"
        },
        {
            id: "admin",
            match: p => p.startsWith("/owner/"),
            name: "AirXpress Admin",
            description: "Quick access to your administration portal.",
            icon: "/static/orders/images/pwa/admin-icon-192.png"
        }
    ];

    const portal = portals.find(item => item.match(path));
    if (!portal) return;

    const isStandalone =
        window.matchMedia("(display-mode: standalone)").matches ||
        window.navigator.standalone === true;

    if (isStandalone) return;

    const dismissalKey = "airxpressInstallDismissed-" + portal.id;

    function wasDismissed() {
        try {
            return localStorage.getItem(dismissalKey) === "yes";
        } catch (error) {
            return false;
        }
    }

    if (wasDismissed()) return;

    if ("serviceWorker" in navigator && window.isSecureContext) {
        navigator.serviceWorker.register("/airxpress-sw.js", {
            scope: "/"
        }).catch(error => {
            console.warn("AirXpress service worker registration failed:", error);
        });
    }

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

            <div id="airxpress-ios-help"
                 style="display:none;font-size:13px;color:#ddd;margin-top:12px;">
                Tap the Share button in Safari, then choose
                <strong>Add to Home Screen</strong>.
            </div>

            <div style="display:flex;gap:10px;margin-top:15px;">
                <button id="airxpress-install-button" type="button"
                    style="flex:1;background:#ff6800;color:#fff;border:0;
                    border-radius:9px;padding:12px;font-weight:700;
                    cursor:pointer;">Install App</button>

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
    const iosHelp = document.getElementById("airxpress-ios-help");

    let installPrompt = null;

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

    window.addEventListener("beforeinstallprompt", function (event) {
        event.preventDefault();
        installPrompt = event;
        window.setTimeout(showBanner, 3000);
    });

    if (isIOS) {
        installButton.style.display = "none";
        iosHelp.style.display = "block";
        window.setTimeout(showBanner, 3000);
    }

    installButton.addEventListener("click", async function () {
        if (!installPrompt) return;

        const promptEvent = installPrompt;
        installPrompt = null;

        try {
            await promptEvent.prompt();
            await promptEvent.userChoice;
            banner.style.display = "none";
        } catch (error) {
            console.warn("AirXpress installation prompt failed:", error);
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
})();
