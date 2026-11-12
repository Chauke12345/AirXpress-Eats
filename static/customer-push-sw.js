/* AirXpress Eats customer push service worker */

self.addEventListener("push", function (event) {
    let payload = {
        title: "AirXpress Eats",
        body: "You have a new notification.",
        url: "/"
    };

    if (event.data) {
        try {
            payload = Object.assign(payload, event.data.json());
        } catch (error) {
            payload.body = event.data.text() || payload.body;
        }
    }

    event.waitUntil(
        self.registration.showNotification(
            payload.title || "AirXpress Eats",
            {
                body: payload.body || "You have a new notification.",
                icon: "/static/orders/images/Airxpress-logo.png",
                badge: "/static/orders/images/Airxpress-logo.png",
                data: { url: payload.url || "/" },
                tag: payload.notification_id
                    ? "customer-notification-" + payload.notification_id
                    : "airxpress-customer-notification",
                renotify: true
            }
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