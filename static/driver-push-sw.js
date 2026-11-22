/* AirXpress Eats driver push service worker */

self.addEventListener("push", function (event) {
    let payload = {
        title: "AirXpress Eats",
        body: "You have a new notification.",
        url: "/driver/dashboard/"
    };

    if (event.data) {
        try {
            payload = Object.assign(payload, event.data.json());
        } catch (error) {
            payload.body = event.data.text() || payload.body;
        }
    }

    event.waitUntil(
        self.registration.showNotification(payload.title || "AirXpress Eats", {
            body: payload.body || "You have a new notification.",
            icon: "/static/orders/images/pwa/driver-icon-192.png",
            badge: "/static/orders/images/pwa/driver-icon-192.png",
            data: { url: payload.url || "/driver/dashboard/" },
            tag: payload.request_id ? "delivery-request-" + payload.request_id : "airxpress-notification",
            renotify: true
        })
    );
});

self.addEventListener("notificationclick", function (event) {
    event.notification.close();

    const requestedUrl = new URL(
        event.notification.data && event.notification.data.url
            ? event.notification.data.url
            : "/driver/dashboard/",
        self.location.origin
    );

    const targetUrl = (
        requestedUrl.origin === self.location.origin &&
        requestedUrl.pathname.startsWith("/driver/")
    )
        ? requestedUrl.href
        : new URL("/driver/dashboard/", self.location.origin).href;

    event.waitUntil(
        self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (clients) {
            for (const client of clients) {
                const clientUrl = new URL(client.url);

                if (
                    clientUrl.origin === self.location.origin &&
                    clientUrl.pathname.startsWith("/driver/") &&
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
