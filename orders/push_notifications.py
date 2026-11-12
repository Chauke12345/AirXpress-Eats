import json
import logging

from django.conf import settings

from pywebpush import WebPushException, webpush

from .models import DriverPushSubscription, CustomerPushSubscription


logger = logging.getLogger(__name__)


def send_driver_push_notification(driver_id, delivery_request_id):
    """Send a generic new-delivery push to every subscription for one driver."""

    public_key = getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", "").strip()
    private_key = getattr(settings, "WEBPUSH_VAPID_PRIVATE_KEY", "")
    subject = getattr(settings, "WEBPUSH_VAPID_SUBJECT", "").strip()

    # Fail safely if push configuration is incomplete.
    if not public_key or not private_key or not subject:
        logger.warning("Driver push skipped: VAPID configuration is incomplete.")
        return 0

    if "REPLACE_WITH_YOUR_SUPPORT_EMAIL" in subject:
        logger.warning("Driver push skipped: configure the VAPID support email.")
        return 0

    # The private key in .env is stored with escaped newline characters.
    private_key = private_key.replace("\\n", "\n").strip()

    subscriptions = DriverPushSubscription.objects.filter(
        driver_id=driver_id
    )

    sent_count = 0

    for subscription in subscriptions.iterator():
        payload = {
            "title": "New delivery request",
            "body": "A delivery request is waiting. Open AirXpress Eats to review it.",
            "url": "/driver/dashboard/#new-request-alert-{}".format(
                delivery_request_id
            ),
            "request_id": delivery_request_id,
        }

        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {
                        "p256dh": subscription.p256dh,
                        "auth": subscription.auth,
                    },
                },
                data=json.dumps(payload),
                vapid_private_key=private_key,
                vapid_claims={"sub": subject},
                ttl=60,
                timeout=10,
            )
            sent_count += 1

        except WebPushException as exc:
            response = getattr(exc, "response", None)
            status_code = getattr(response, "status_code", None)

            if status_code in (404, 410):
                subscription.delete()
                logger.info(
                    "Removed expired push subscription for driver %s.",
                    driver_id,
                )
            else:
                logger.warning(
                    "Push delivery failed for driver %s, subscription %s; "
                    "HTTP status: %s.",
                    driver_id,
                    subscription.pk,
                    status_code or "unknown",
                )

        except Exception:
            logger.exception(
                "Unexpected push error for driver %s, subscription %s.",
                driver_id,
                subscription.pk,
            )

    return sent_count


def send_customer_push_notification(
    customer_id,
    title,
    body,
    url="/",
    notification_id=None,
):
    """Send a push notification to all registered devices for a customer."""

    public_key = getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", "").strip()
    private_key = getattr(settings, "WEBPUSH_VAPID_PRIVATE_KEY", "")
    subject = getattr(settings, "WEBPUSH_VAPID_SUBJECT", "").strip()

    if not public_key or not private_key or not subject:
        logger.warning(
            "Customer push skipped: VAPID configuration is incomplete."
        )
        return 0

    if "REPLACE_WITH_YOUR_SUPPORT_EMAIL" in subject:
        logger.warning(
            "Customer push skipped: configure the VAPID support email."
        )
        return 0

    private_key = private_key.replace("\\n", "\n").strip()

    subscriptions = CustomerPushSubscription.objects.filter(
        customer_id=customer_id
    )

    sent_count = 0

    payload = {
        "title": title,
        "body": body,
        "url": url,
        "notification_id": notification_id,
    }

    for subscription in subscriptions.iterator():
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {
                        "p256dh": subscription.p256dh,
                        "auth": subscription.auth,
                    },
                },
                data=json.dumps(payload),
                vapid_private_key=private_key,
                vapid_claims={"sub": subject},
                ttl=3600,
                timeout=10,
            )
            sent_count += 1

        except WebPushException as exc:
            response = getattr(exc, "response", None)
            status_code = getattr(response, "status_code", None)

            if status_code in (404, 410):
                subscription.delete()
                logger.info(
                    "Removed expired push subscription for customer %s.",
                    customer_id,
                )
            else:
                logger.warning(
                    "Customer push failed for customer %s, subscription %s; "
                    "HTTP status: %s.",
                    customer_id,
                    subscription.pk,
                    status_code or "unknown",
                )

        except Exception:
            logger.exception(
                "Unexpected customer push error for customer %s, "
                "subscription %s.",
                customer_id,
                subscription.pk,
            )

    return sent_count