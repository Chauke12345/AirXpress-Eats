(function () {
    "use strict";

    const DISMISS_KEY = "airxpressInstallDismissedV2";

    function addAppMetadata() {
        if (!document.querySelector('link[rel="manifest"]')) {
            const link = document.createElement("link");
            link.rel = "manifest";
            link.href = "/static/orders/airxpress.webmanifest";
            document.head.appendChild(link);
        }

        if (!document.querySelector('meta[name="theme-color"]')) {
            const meta = document.createElement("meta");
            meta.name = "theme-color";
            meta.content = "#ff6800";
            document.head.appendChild(meta);
        }

        if (!document.querySelector('link[rel="apple-touch-icon"]')) {
            const icon = document.createElement("link");
            icon.rel = "apple-touch-icon";
            icon.href = "/static/orders/images/Airxpress-icon-192.png";
            document.head.appendChild(icon);
        }
    }

    addAppMetadata();

    // All portals use exactly the same root-scoped service worker.
    if ("serviceWorker" in navigator && window.isSecureContext) {
        navigator.serviceWorker.register("/airxpress-sw.js", { scope: "/" })
            .catch(function (error) {
                console.warn("AirXpress service worker registration failed:", error);
            });
    }

    // Do not show an install invitation inside an installed app.
    if (
        window.matchMedia("(display-mode: standalone)").matches ||
        window.navigator.standalone === true
    ) {
        return;
    }

    // Prevent duplicate banners if this script is included more than once.
    if (document.getElementById("airxpress-install-banner")) {
        return;
    }

    let installPrompt = null;
    let bannerTimer = null;

    const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent) ||
        (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

    const isAndroid = /android/i.test(navigator.userAgent);
    const isChrome = /chrome|chromium/i.test(navigator.userAgent) &&
        !/edg|opr|samsungbrowser/i.test(navigator.userAgent);

    const markup = `
        <div id="airxpress-install-banner"
             role="dialog"
             aria-label="Install AirXpress Eats"
             style="display:none;position:fixed;top:50%;left:50%;
             transform:translate(-50%,-50%);width:calc(100% - 32px);
             max-width:460px;background:#141414;color:#fff;
             border:1px solid #ff6800;border-radius:16px;padding:18px;
             z-index:999999;box-shadow:0 8px 30px rgba(0,0,0,.55);
             font-family:Arial,sans-serif;">

            <div style="display:flex;align-items:center;gap:12px;">
                <img src="/static/orders/images/Airxpress-icon-192.png"
                     alt="AirXpress Eats"
                     style="width:54px;height:54px;object-fit:contain;
                     border-radius:12px;">

                <div style="flex:1;">
                    <strong style="font-size:16px;">
                        Get the AirXpress Eats App!
                    </strong>
                    <div style="font-size:13px;color:#ccc;margin-top:5px;">
                        Quick access to your orders and account.
                    </div>
                </div>

                <button id="airxpress-dismiss" type="button"
                    aria-label="Close"
                    style="background:transparent;color:#fff;border:0;
                    font-size:24px;cursor:pointer;">&times;</button>
            </div>

            <div id="airxpress-install-help"
                 style="font-size:13px;color:#ddd;margin-top:14px;">
                Install AirXpress Eats on your device.
            </div>

            <div style="display:flex;gap:10px;margin-top:15px;">
                <button id="airxpress-install-button" type="button"
                    style="flex:1;background:#ff6800;color:#fff;border:0;
                    border-radius:9px;padding:12px;font-weight:700;
                    cursor:pointer;">
                    Install App
                </button>

                <button id="airxpress-later" type="button"
                    style="background:#292929;color:#fff;border:0;
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

    function wasDismissed() {
        try {
            return sessionStorage.getItem(DISMISS_KEY) === "yes";
        } catch (error) {
            return false;
        }
    }

    function showBanner() {
        if (!wasDismissed()) {
            banner.style.display = "block";
        }
    }

    function hideBanner() {
        banner.style.display = "none";
    }

    function dismissBanner() {
        hideBanner();
        try {
            sessionStorage.setItem(DISMISS_KEY, "yes");
        } catch (error) {}
    }

    function showManualInstructions() {
        if (isIOS) {
            help.innerHTML =
                'In Safari, tap the <strong>Share</strong> button, ' +
                'then select <strong>Add to Home Screen</strong>.';
        } else if (isAndroid && isChrome) {
            help.innerHTML =
                'In Chrome, open the <strong>three-dot menu</strong> ' +
                'and select <strong>Install app</strong> or ' +
                '<strong>Add to Home screen</strong>.';
        } else {
            help.innerHTML =
                'Open your browser menu and look for ' +
                '<strong>Install app</strong> or ' +
                '<strong>Add to Home Screen</strong>.';
        }
    }

    // Capture the browser's native install opportunity.
    window.addEventListener("beforeinstallprompt", function (event) {
        event.preventDefault();
        installPrompt = event;
        installButton.textContent = "Install App";
        help.textContent = "Install AirXpress Eats on this device.";
        installButton.style.display = "block";
    });

    // Always provide a useful manual installation route.
    if (isIOS) {
        installButton.textContent = "How to install";
        showManualInstructions();
    } else {
        installButton.textContent = "Install App";
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
        .addEventListener("click", dismissBanner);

    document.getElementById("airxpress-later")
        .addEventListener("click", dismissBanner);

    window.addEventListener("appinstalled", hideBanner);

    // Automatic invitation after the page has loaded.
    bannerTimer = window.setTimeout(showBanner, 2500);
})();
