(function () {
    "use strict";

    const path = window.location.pathname.toLowerCase();

    const portals = [
        {
            id: "customer",
            match: p => p === "/" || p.startsWith("/customer/") || p.startsWith("/shop/"),
            name: "AirXpress Customer",
            description: "Order your favourite meals with AirXpress Eats.",
            icon: "/static/orders/images/pwa/customer-icon.png",
            manifest: "/static/orders/customer.webmanifest"
        },
        {
            id: "driver",
            match: p => p.startsWith("/driver/"),
            name: "AirXpress Driver",
            description: "Access your delivery driver portal.",
            icon: "/static/orders/images/pwa/driver-icon.png",
            manifest: "/static/orders/driver.webmanifest"
        },
        {
            id: "merchant",
            match: p => p.startsWith("/merchant/") || p.startsWith("/staff/"),
            name: "AirXpress Shops",
            description: "Manage your shop and customer orders.",
            icon: "/static/orders/images/pwa/merchant-icon.png",
            manifest: "/static/orders/merchant.webmanifest"
        },
        {
            id: "admin",
            match: p => p.startsWith("/owner/"),
            name: "AirXpress Admin",
            description: "Manage your AirXpress Eats platform.",
            icon: "/static/orders/images/pwa/admin-icon.png",
            manifest: "/static/orders/admin.webmanifest"
        }
    ];

    const portal = portals.find(item => item.match(path));
    if (!portal) return;

    const isStandalone = window.matchMedia("(display-mode: standalone)").matches ||
        window.navigator.standalone === true;

    if (isStandalone) return;

    const dismissalKey = "airxpress-install-dismissed-" + portal.id;
    const dismissedAt = Number(localStorage.getItem(dismissalKey) || 0);
    const sevenDays = 7 * 24 * 60 * 60 * 1000;

    if (dismissedAt && Date.now() - dismissedAt < sevenDays) return;

    let manifestLink = document.querySelector('link[rel="manifest"]');
    if (!manifestLink) {
        manifestLink = document.createElement("link");
        manifestLink.rel = "manifest";
        document.head.appendChild(manifestLink);
    }
    manifestLink.href = portal.manifest;

    if ("serviceWorker" in navigator && window.isSecureContext) {
        navigator.serviceWorker.register("/airxpress-sw.js", {
            scope: "/"
        }).catch(error => {
            console.warn("AirXpress service worker registration failed:", error);
        });
    }

    const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent) ||
        (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

    let installPrompt = null;

    const markup = `
        <div id="airxpress-install-banner"
             role="dialog"
             aria-label="Install ${portal.name}"
             style="display:none;position:fixed;left:50%;bottom:22px;
             transform:translateX(-50%);width:calc(100% - 28px);
             max-width:460px;background:#101010;color:#fff;
             border:2px solid #aeb2b8;border-radius:18px;
             padding:19px;z-index:999999;
             box-shadow:0 10px 35px rgba(0,0,0,.65);
             font-family:Arial,sans-serif;">

            <div style="display:flex;align-items:center;gap:13px;">
                <img src="${portal.icon}" alt=""
                     style="width:58px;height:58px;object-fit:contain;
                     border-radius:12px;background:#080808;">

                <div style="flex:1;">
                    <strong style="font-size:17px;">${portal.name}</strong>
                    <div style="font-size:13px;color:#c6c6c6;margin-top:6px;">
                        ${portal.description}
                    </div>
                </div>

                <button id="airxpress-dismiss" type="button"
                    aria-label="Close"
                    style="background:transparent;color:#fff;border:0;
                    font-size:25px;cursor:pointer;">&times;</button>
            </div>

            <div id="airxpress-install-help"
                 style="font-size:13px;color:#ddd;margin-top:15px;">
                Add this app to your home screen for quick access.
            </div>

            <div style="display:flex;gap:10px;margin-top:15px;">
                <button id="airxpress-install-button" type="button"
                    style="flex:1;background:linear-gradient(135deg,#fff,#aaa);
                    color:#080808;border:0;border-radius:9px;
                    padding:13px;font-weight:700;cursor:pointer;">
                    Install App
                </button>

                <button id="airxpress-later" type="button"
                    style="background:#292929;color:#fff;border:1px solid #777;
                    border-radius:9px;padding:12px 16px;cursor:pointer;">
                    Not now
                </button>
            </div>
        </div>`;

    document.body.insertAdjacentHTML("beforeend", markup);

    const banner = document.getElementById("airxpress-install-banner");
    const installButton = document.getElementById("airxpress-install-button");
    const help = document.getElementById("airxpress-install-help");

    function showBanner() {
        if (!isStandalone) banner.style.display = "block";
    }

    function hideBanner() {
        banner.style.display = "none";
    }

    function dismissBanner() {
        localStorage.setItem(dismissalKey, String(Date.now()));
        hideBanner();
    }

    function showManualInstructions() {
        if (isIOS) {
            help.innerHTML =
                'In Safari, tap <strong>Share</strong>, then ' +
                '<strong>Add to Home Screen</strong>.';
        } else {
            help.innerHTML =
                'Open your browser menu and choose ' +
                '<strong>Install app</strong> or ' +
                '<strong>Add to Home Screen</strong>.';
        }
    }

    window.addEventListener("beforeinstallprompt", event => {
        event.preventDefault();
        installPrompt = event;
        installButton.textContent = "Install App";
        help.textContent = "Install " + portal.name + " on this device.";
    });

    window.addEventListener("appinstalled", () => {
        localStorage.removeItem(dismissalKey);
        hideBanner();
    });

    if (isIOS) {
        installButton.textContent = "How to install";
        showManualInstructions();
    }

    installButton.addEventListener("click", async () => {
        if (!installPrompt) {
            showManualInstructions();
            return;
        }

        try {
            const promptEvent = installPrompt;
            installPrompt = null;
            await promptEvent.prompt();

            const choice = await promptEvent.userChoice;
            if (choice && choice.outcome === "accepted") {
                hideBanner();
            }
        } catch (error) {
            console.warn("AirXpress installation prompt failed:", error);
            showManualInstructions();
        }
    });

    document.getElementById("airxpress-dismiss")
        .addEventListener("click", dismissBanner);

    document.getElementById("airxpress-later")
        .addEventListener("click", dismissBanner);

    window.setTimeout(showBanner, 2500);
})();
