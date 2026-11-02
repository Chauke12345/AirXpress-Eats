import logging
from decimal import Decimal, ROUND_HALF_UP

import requests
from django.conf import settings


logger = logging.getLogger(__name__)

YOCO_CHECKOUTS_URL = "https://payments.yoco.com/api/checkouts"
YOCO_TIMEOUT_SECONDS = 20


class YocoError(Exception):
    """Raised when Yoco checkout creation fails."""


def create_checkout(order, success_url, cancel_url, failure_url):
    """
    Create a hosted Yoco checkout for one existing AirXpress order.

    The order remains pending until a verified webhook confirms payment.
    """
    secret_key = getattr(settings, "YOCO_SECRET_KEY", "").strip()

    if not secret_key:
        raise YocoError("Yoco secret key is not configured.")

    total = order.final_total

    if total is None or total <= Decimal("0.00"):
        raise YocoError("Order has no valid payment amount.")

    amount_cents = int(
        (total * Decimal("100")).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )

    payload = {
        "amount": amount_cents,
        "currency": "ZAR",
        "successUrl": success_url,
        "cancelUrl": cancel_url,
        "failureUrl": failure_url,
        "metadata": {
            "orderId": str(order.pk),
        },
    }

    try:
        response = requests.post(
            YOCO_CHECKOUTS_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {secret_key}",
                "Content-Type": "application/json",
            },
            timeout=YOCO_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, dict):
            raise YocoError("Yoco returned an invalid response.")
    except requests.RequestException as exc:
        logger.warning(
            "Yoco checkout request failed for order %s: %s",
            order.pk,
            type(exc).__name__,
        )
        raise YocoError(
            "Could not connect to Yoco to create checkout."
        ) from exc
    except ValueError as exc:
        raise YocoError(
            "Yoco returned an invalid response."
        ) from exc

    checkout_url = data.get("redirectUrl")
    checkout_id = data.get("id")

    if not checkout_url or not checkout_id:
        raise YocoError(
            "Yoco response did not contain a checkout ID and redirect URL."
        )

    if not checkout_url.startswith("https://"):
        raise YocoError("Yoco returned an invalid checkout URL.")

    return {
        "checkout_id": str(checkout_id),
        "redirect_url": checkout_url,
    }
