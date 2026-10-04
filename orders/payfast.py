import hashlib
from urllib.parse import quote_plus

from django.conf import settings


PAYFAST_SIGNATURE_FIELDS = [
    "merchant_id",
    "merchant_key",
    "return_url",
    "cancel_url",
    "notify_url",
    "notify_method",
    "name_first",
    "name_last",
    "email_address",
    "cell_number",
    "m_payment_id",
    "amount",
    "item_name",
    "item_description",
    "custom_int1",
    "custom_int2",
    "custom_int3",
    "custom_int4",
    "custom_int5",
    "custom_str1",
    "custom_str2",
    "custom_str3",
    "custom_str4",
    "custom_str5",
    "email_confirmation",
    "confirmation_address",
    "currency",
    "payment_method",
    "subscription_type",
    "passphrase",
    "billing_date",
    "recurring_amount",
    "frequency",
    "cycles",
    "subscription_notify_email",
    "subscription_notify_webhook",
    "subscription_notify_buyer",
]


def get_payfast_url():
    """
    Return the correct PayFast payment endpoint.
    """
    if settings.PAYFAST_SANDBOX:
        return "https://sandbox.payfast.co.za/eng/process"

    return "https://www.payfast.co.za/eng/process"


def generate_signature(data):
    """
    Generate a PayFast custom-integration MD5 signature.

    PayFast requires the checkout fields to be processed in the
    documented field order, with values trimmed and URL-encoded.
    The passphrase is appended as the final signing field when set.
    """

    signature_data = {}

    for field in PAYFAST_SIGNATURE_FIELDS:
        if field == "passphrase":
            continue

        if field not in data:
            continue

        value = data.get(field)

        if value is None:
            continue

        value = str(value).strip()

        if value == "":
            continue

        signature_data[field] = value

    passphrase = settings.PAYFAST_PASSPHRASE.strip()

    if passphrase:
        signature_data["passphrase"] = passphrase

    parameter_string = "&".join(
        f"{key}={quote_plus(str(value).strip(), safe="")}"
        for key, value in signature_data.items()
    )

    return hashlib.md5(
        parameter_string.encode("utf-8")
    ).hexdigest()


def build_payment_data(
    order,
    return_url,
    cancel_url,
    notify_url,
):
    """
    Build the PayFast custom integration request.
    """

    customer_name = (
        order.customer_name or ""
    ).strip()

    name_parts = customer_name.split(
        " ",
        1,
    )

    first_name = (
        name_parts[0]
        if name_parts
        else ""
    )

    last_name = (
        name_parts[1]
        if len(name_parts) > 1
        else ""
    )

    data = {
        "merchant_id": settings.PAYFAST_MERCHANT_ID,
        "merchant_key": settings.PAYFAST_MERCHANT_KEY,
        "return_url": return_url,
        "cancel_url": cancel_url,
        "notify_url": notify_url,
        "name_first": first_name,
        "name_last": last_name,
        "m_payment_id": str(order.id),
        "amount": f"{order.final_total:.2f}",
        "item_name": (
            f"AirXpress Eats Order #{order.id}"
        ),
        "item_description": (
            f"Food order from {order.shop.name}"
        ),
    }

    data["signature"] = generate_signature(
        data
    )

    return data

