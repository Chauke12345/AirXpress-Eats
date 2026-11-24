(function () {
    "use strict";

    if (window.__airxpressPerformanceMonitorLoaded) return;
    window.__airxpressPerformanceMonitorLoaded = true;

    const state = {
        mode: "normal",
        warnings: 0,
        longTasks: 0,
        pageReported: false
    };

    function classifyDevice() {
        const ua = navigator.userAgent || "";
        if (/iPad|Tablet/i.test(ua)) return "tablet";
        if (/Mobi|Android/i.test(ua)) return "mobile";
        return "desktop";
    }

    function classifyBrowser() {
        const ua = navigator.userAgent || "";
        if (/Edg/i.test(ua)) return "edge";
        if (/SamsungBrowser/i.test(ua)) return "samsung";
        if (/OPR|Opera/i.test(ua)) return "opera";
        if (/Firefox/i.test(ua)) return "firefox";
        if (/Chrome|CriOS/i.test(ua)) return "chrome";
        if (/Safari/i.test(ua)) return "safari";
        return "other";
    }

    function classifyOS() {
        const ua = navigator.userAgent || "";
        if (/Android/i.test(ua)) return "android";
        if (/iPhone|iPad|iPod/i.test(ua)) return "ios";
        if (/Windows/i.test(ua)) return "windows";
        if (/Mac OS/i.test(ua)) return "macos";
        if (/Linux/i.test(ua)) return "linux";
        return "other";
    }

    function getPageCategory() {
        const path = location.pathname.toLowerCase();
        if (path.includes("track")) return "tracking";
        if (path.includes("checkout")) return "checkout";
        if (path.includes("cart")) return "cart";
        if (path.includes("menu") || path.includes("shop")) return "menu";
        if (path.includes("account") || path.includes("login")) return "account";
        if (path === "/" || path.includes("home")) return "home";
        return "other";
    }

    function getCSRFToken() {
        const input = document.querySelector(
            'input[name="csrfmiddlewaretoken"]'
        );
        if (input) return input.value;

        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    function report(issue, responseTime) {
        if (state.pageReported) return;
        state.pageReported = true;

        const token = getCSRFToken();
        if (!token) return;

        const payload = {
            device_category: classifyDevice(),
            browser_family: classifyBrowser(),
            os_family: classifyOS(),
            performance_mode: state.mode,
            issue_type: issue,
            page_path: getPageCategory(),
            response_time_ms: Number.isInteger(responseTime)
                ? Math.max(0, Math.min(responseTime, 120000))
                : null
        };

        fetch("/customer/device-performance/report/", {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": token
            },
            body: JSON.stringify(payload),
            keepalive: true
        }).catch(function () {});
    }

    function showLiteNotice() {
        if (document.getElementById("ax-performance-notice")) return;

        const notice = document.createElement("div");
        notice.id = "ax-performance-notice";
        notice.setAttribute("role", "status");
        notice.setAttribute("aria-live", "polite");
        notice.textContent =
            "We've adjusted a few visual effects to help AirXpress Eats run more smoothly. Ordering and payments remain available.";

        Object.assign(notice.style, {
            position: "fixed",
            left: "16px",
            right: "16px",
            bottom: "16px",
            zIndex: "99999",
            padding: "14px 18px",
            background: "#173b32",
            color: "#ffffff",
            borderRadius: "12px",
            fontSize: "14px",
            lineHeight: "1.5",
            boxShadow: "0 4px 18px rgba(0,0,0,.2)"
        });

        document.body.appendChild(notice);

        window.setTimeout(function () {
            notice.remove();
        }, 8000);
    }

    function enableLiteMode() {
        if (state.mode !== "normal") return;

        state.mode = "lite";
        document.documentElement.classList.add("ax-lite-mode");

        try {
            sessionStorage.setItem("ax_performance_mode", "lite");
        } catch (error) {}

        showLiteNotice();
        report("slow_page");
    }

    function assessDevice() {
        let weakSignals = 0;

        if (
            typeof navigator.deviceMemory === "number" &&
            navigator.deviceMemory <= 2
        ) weakSignals++;

        if (
            typeof navigator.hardwareConcurrency === "number" &&
            navigator.hardwareConcurrency <= 2
        ) weakSignals++;

        const connection =
            navigator.connection ||
            navigator.mozConnection ||
            navigator.webkitConnection;

        if (
            connection &&
            ["slow-2g", "2g"].includes(connection.effectiveType)
        ) weakSignals++;

        if (connection && connection.saveData) weakSignals++;

        state.warnings = weakSignals;

        if (weakSignals >= 2) {
            enableLiteMode();
        }
    }

    function monitorPerformance() {
        if ("PerformanceObserver" in window) {
            try {
                const observer = new PerformanceObserver(function (list) {
                    state.longTasks += list.getEntries().length;

                    if (state.longTasks >= 3) {
                        report("long_task");
                        enableLiteMode();
                    }
                });

                observer.observe({ type: "longtask", buffered: true });
            } catch (error) {}
        }

        window.addEventListener("error", function () {
            report("javascript_error");
        });

        window.addEventListener("load", function () {
            window.setTimeout(function () {
                const navigation =
                    performance.getEntriesByType("navigation")[0];

                const duration = navigation
                    ? Math.round(navigation.loadEventEnd)
                    : null;

                if (duration && duration > 5000) {
                    enableLiteMode();
                    report("slow_page", duration);
                }
            }, 500);
        }, { once: true });
    }

    try {
        if (sessionStorage.getItem("ax_performance_mode") === "lite") {
            state.mode = "lite";
            document.documentElement.classList.add("ax-lite-mode");
        }
    } catch (error) {}

    assessDevice();
    monitorPerformance();
})();
