(function () {
    "use strict";

    const path = window.location.pathname.toLowerCase();

    const portals = [
        {
            match: function (path) {
                return path === "/" ||
                    path.startsWith("/customer/") ||
                    path.startsWith("/shop/");
            },
            name: "AirXpress Customer",
            description: "Order your favourite meals with AirXpress Eats.",
            icon: "/static/orders/images/pwa/customer-icon.png",
            manifest: "/static/orders/customer.webmanifest"
        },
        {
            match: function (path) {
                return path.startsWith("/driver/");
            },
            name: "AirXpress Driver",
            description: "Access your delivery driver portal.",
            icon: "/static/orders/images/pwa/driver-icon.png",
            manifest: "/static/orders/driver.webmanifest"
        },
        {
            match: function (path) {
                return path.startsWith("/merchant/") ||
                    path.startsWith("/staff/");
            },
            name: "AirXpress Shops",
            description: "Manage your shop and customer orders.",
            icon: "/static/orders/images/pwa/merchant-icon.png",
            manifest: "/static/orders/merchant.webmanifest"
        },
        {
            match: function (path) {
                return path.startsWith("/owner/");
            },
            name: "AirXpress Admin",
            description: "Manage your AirXpress Eats platform.",
            icon: "/static/orders/images/pwa/admin-icon.png",
            manifest: "/static/orders/admin.webmanifest"
        }
    ];

    const portal = portals.find(function (item) {
        return typeof item.match === "function"
            ? item.match(path)
            : path.startsWith(item.match);
    });

    if (!portal) return;

    let manifestLink = document.querySelector('link[rel="manifest"]');

    if (!manifestLink) {
        manifestLink = document.createElement("link");
        manifestLink.rel = "manifest";
        document.head.appendChild(manifestLink);
    }

    manifestLink.href = portal.manifest;

    if (!document.querySelector('meta[name="theme-color"]')) {
        const meta = document.createElement("meta");
        meta.name = "theme-color";
        meta.content = "#000000";
        document.head.appendChild(meta);
    }

    if ("serviceWorker" in navigator && window.isSecureContext) {
        navigator.serviceWorker.register("/airxpress-sw.js", {
            scope: "/"
        }).catch(function (error) {
            console.warn("AirXpress service worker registration failed:", error);
        });
    }

    if (
        window.matchMedia("(display-mode: standalone)").matches ||
        window.navigator.standalone === true
    ) {
        return;
    }

    if (document.getElementById("airxpress-install-banner")) return;

    let installPrompt = null;

    const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent) ||
        (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

    const isAndroid = /android/i.test(navigator.userAgent);
    const isChrome = /chrome|chromium/i.test(navigator.userAgent) &&
        !/edg|opr|samsungbrowser/i.test(navigator.userAgent);

    const markup = `
        <div id="airxpress-install-banner"
             role="dialog"
             aria-label="Install ${portal.name}"
             style="display:none;position:fixed;top:50%;left:50%;
             transform:translate(-50%,-50%);width:calc(100% - 32px);
             max-width:460px;background:#101010;color:#fff;
             border:2px solid #aeb2b8;border-radius:18px;padding:20px;
             z-index:999999;box-shadow:0 10px 35px rgba(0,0,0,.65);
             font-family:Arial,sans-serif;">

            <div style="display:flex;align-items:center;gap:13px;">
                <img src="${portal.icon}" alt="${portal.name}"
                     style="width:62px;height:62px;object-fit:contain;
                     border-radius:12px;background:#080808;">

                <div style="flex:1;">
                    <strong style="font-size:17px;">
                        ${portal.name}
                    </strong>
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
                 style="font-size:13px;color:#ddd;margin-top:16px;">
                Install ${portal.name} on your device for quick access.
            </div>

            <div style="display:flex;gap:10px;margin-top:16px;">
                <button id="airxpress-install-button" type="button"
                    style="flex:1;background:linear-gradient(135deg,#fff,#888);
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
        </div>
    `;

    document.body.insertAdjacentHTML("beforeend", markup);

    const banner = document.getElementById("airxpress-install-banner");
    const installButton = document.getElementById("airxpress-install-button");
    const help = document.getElementById("airxpress-install-help");

    function showBanner() {
        banner.style.display = "block";
    }

    function hideBanner() {
        banner.style.display = "none";
    }

    function showManualInstructions() {
        if (isIOS) {
            help.innerHTML =
                'In Safari, tap <strong>Share</strong>, then ' +
                '<strong>Add to Home Screen</strong>.';
        } else if (isAndroid && isChrome) {
            help.innerHTML =
                'In Chrome, open the <strong>three-dot menu</strong> ' +
                'and select <strong>Install app</strong>.';
        } else {
            help.innerHTML =
                'Open your browser menu and look for ' +
                '<strong>Install app</strong> or ' +
                '<strong>Add to Home Screen</strong>.';
        }
    }

    window.addEventListener("beforeinstallprompt", function (event) {
        event.preventDefault();
        installPrompt = event;
        installButton.textContent = "Install App";
        help.textContent = "Install " + portal.name + " on this device.";
    });

    if (isIOS) {
        installButton.textContent = "How to install";
        showManualInstructions();
    }

    installButton.addEventListener("click", async function () {
        if (!installPrompt) {
            showManualInstructions();
            return;
        }

        try {
            installPrompt.prompt();
            const choice = await installPrompt.userChoice;

            if (choice && choice.outcome === "accepted") {
                hideBanner();
            }
        } catch (error) {
            console.warn("AirXpress installation prompt:", error);
            showManualInstructions();
        } finally {
            installPrompt = null;
        }
    });

    document.getElementById("airxpress-dismiss")
        .addEventListener("click", hideBanner);

    document.getElementById("airxpress-later")
        .addEventListener("click", hideBanner);

    window.addEventListener("appinstalled", hideBanner);

    window.setTimeout(showBanner, 2500);
})();


