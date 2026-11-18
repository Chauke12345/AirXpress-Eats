/* AIRXPRESS EATS - UNIFIED ROOT SERVICE WORKER */

self.addEventListener("install", function (event) {
    self.skipWaiting();
});

self.addEventListener("activate", function (event) {
    event.waitUntil(self.clients.claim());
});

self.addEventListener("push", function (event) {
    let payload = {
        title: "AirXpress Eats",
        body: "You have a new update.",
        url: "/"
    };

    if (event.data) {
        try {
            payload = Object.assign(payload, event.data.json());
        } catch (error) {
            payload.body = event.data.text() || payload.body;
        }
    }

    const isDriver = Boolean(payload.request_id);
    const defaultUrl = isDriver ? "/driver/dashboard/" : "/";

    const notificationOptions = {
        body: payload.body || "You have a new update.",
        icon: "/static/orders/images/Airxpress-icon-192.png",
        badge: "/static/orders/images/Airxpress-icon-192.png",
        data: {
            url: payload.url || defaultUrl
        },
        tag: payload.notification_id
            ? "customer-" + payload.notification_id
            : payload.request_id
                ? "driver-" + payload.request_id
                : "airxpress-notification",
        renotify: true
    };

    event.waitUntil(
        self.registration.showNotification(
            payload.title || "AirXpress Eats",
            notificationOptions
        )
    );
});

self.addEventListener("notificationclick", function (event) {
    event.notification.close();

    const targetUrl = new URL(
        event.notification.data && event.notification.data.url
            ? event.notification.data.url
            : "/",
        self.location.origin
    ).href;

    event.waitUntil(
        self.clients.matchAll({
            type: "window",
            includeUncontrolled: true
        }).then(function (clients) {
            for (const client of clients) {
                if (
                    client.url.startsWith(self.location.origin) &&
                    "focus" in client
                ) {
                    return client.navigate(targetUrl).then(function (focusedClient) {
                        return (focusedClient || client).focus();
                    });
                }
            }

            return self.clients.openWindow(targetUrl);
        })
    );
});
