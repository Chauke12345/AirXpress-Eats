(function () {
    "use strict";

    const script = document.currentScript;
    if (!script) return;

    // Only registered, authenticated customers can save or resume a journey.
    const isRegisteredCustomer =
        script.dataset.customerAuthenticated === "true";

    if (!isRegisteredCustomer) return;

    const page = script.dataset.page;
    const shopSlug = script.dataset.shopSlug || "";
    const shopName = script.dataset.shopName || "your restaurant";
    const STORAGE_KEY = "airxpress_customer_journey_v1";
    const MAX_AGE = 30 * 24 * 60 * 60 * 1000;

    function readJourney() {
        try {
            return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
        } catch (error) {
            return {};
        }
    }

    function saveJourney(data) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
        } catch (error) {
            console.warn("AirXpress journey could not be saved.");
        }
    }

    let journey = readJourney();

    // Remember the restaurant menu and its scroll position.
    if (page === "menu" && shopSlug) {
        const currentUrl = new URL(window.location.href);
        const isResume = currentUrl.searchParams.get("resume") === "1";

        currentUrl.searchParams.delete("resume");

        journey.menuUrl = currentUrl.pathname + currentUrl.search;
        journey.shopSlug = shopSlug;
        journey.shopName = shopName;
        journey.updatedAt = Date.now();

        saveJourney(journey);

        // Restore scroll only when the customer explicitly resumes.
        if (isResume) {
            const savedPosition = Number(journey.menuScrollY) || 0;

            currentUrl.searchParams.delete("resume");
            window.history.replaceState(
                {},
                "",
                currentUrl.pathname + currentUrl.search + currentUrl.hash
            );

            requestAnimationFrame(function () {
                requestAnimationFrame(function () {
                    window.scrollTo(0, savedPosition);
                });
            });
        }

        let saveTimer;

        function savePosition() {
            clearTimeout(saveTimer);

            saveTimer = setTimeout(function () {
                journey.menuScrollY = Math.max(
                    0,
                    window.scrollY || window.pageYOffset || 0
                );
                journey.updatedAt = Date.now();
                saveJourney(journey);
            }, 250);
        }

        window.addEventListener("scroll", savePosition, { passive: true });
        window.addEventListener("pagehide", savePosition);
    }

    // Keep track of cart and checkout without making checkout
    // the automatic resume destination.
    if (page === "cart" || page === "checkout") {
        journey.lastPage = page;
        journey.updatedAt = Date.now();
        saveJourney(journey);
    }

    // Show a Continue option on the homepage.
    if (page === "home") {
        if (
            !journey.menuUrl ||
            !journey.shopSlug ||
            !journey.updatedAt ||
            Date.now() - journey.updatedAt > MAX_AGE
        ) {
            return;
        }

        const target = new URL(journey.menuUrl, window.location.origin);
        target.searchParams.set("resume", "1");

        const banner = document.createElement("div");
        banner.id = "airxpress-continue-browsing";

        banner.innerHTML = `
            <div class="ax-continue-content">
                <div>
                    <strong>Continue where you left off</strong>
                    <span></span>
                </div>
                <a class="ax-continue-link">Continue</a>
                <button type="button" aria-label="Dismiss">×</button>
            </div>
        `;

        banner.querySelector("span").textContent =
            "You were browsing " + journey.shopName + ".";

        banner.querySelector("a").href = target.toString();

        banner.querySelector("button").addEventListener("click", function () {
            banner.remove();
        });

        const style = document.createElement("style");
        style.textContent = `
            #airxpress-continue-browsing {
                position: fixed;
                z-index: 9998;
                bottom: 18px;
                left: 50%;
                transform: translateX(-50%);
                width: calc(100% - 28px);
                max-width: 520px;
                background: #171717;
                color: white;
                border: 1px solid #ff6800;
                border-radius: 16px;
                padding: 14px;
                box-shadow: 0 8px 30px rgba(0,0,0,.3);
                font-family: Arial, sans-serif;
            }
            #airxpress-continue-browsing .ax-continue-content {
                display: flex;
                align-items: center;
                gap: 12px;
            }
            #airxpress-continue-browsing .ax-continue-content > div {
                flex: 1;
                min-width: 0;
            }
            #airxpress-continue-browsing strong,
            #airxpress-continue-browsing span {
                display: block;
            }
            #airxpress-continue-browsing strong {
                font-size: 14px;
                margin-bottom: 5px;
            }
            #airxpress-continue-browsing span {
                font-size: 12px;
                color: #ccc;
            }
            #airxpress-continue-browsing .ax-continue-link {
                background: #ff6800;
                color: white;
                text-decoration: none;
                font-weight: bold;
                font-size: 13px;
                padding: 11px 14px;
                border-radius: 10px;
                white-space: nowrap;
            }
            #airxpress-continue-browsing button {
                background: transparent;
                color: white;
                border: 0;
                font-size: 23px;
                cursor: pointer;
                padding: 2px 5px;
            }
        `;

        document.head.appendChild(style);
        document.body.appendChild(banner);
    }
})();