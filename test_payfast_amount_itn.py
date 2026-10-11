import hashlib
from urllib.parse import quote_plus
from unittest.mock import patch

from django.conf import settings
from django.test import Client
from orders.models import Order

order = Order.objects.get(id=26)
before = (order.payment_status, order.status)

data = {
    "m_payment_id": "26",
    "merchant_id": str(settings.PAYFAST_MERCHANT_ID),
    "amount_gross": "1.00",
    "payment_status": "COMPLETE",
    "item_name": "Local amount test",
    "item_description": "",
}

parameter_string = "&".join(
    f"{key}={quote_plus(str(value).strip(), safe='')}"
    for key, value in data.items()
    if value is not None
)

passphrase = (settings.PAYFAST_PASSPHRASE or "").strip()
if passphrase:
    parameter_string += "&passphrase=" + quote_plus(passphrase, safe="")

data["signature"] = hashlib.md5(
    parameter_string.encode("utf-8")
).hexdigest()

client = Client(HTTP_HOST="127.0.0.1")

with patch("orders.payfast.validate_itn_with_payfast", return_value=True):
    response = client.post("/payment/payfast/itn/", data)

order.refresh_from_db()

print("HTTP status:", response.status_code)
print("ITN response:", response.content.decode())
print("Payment status:", order.payment_status)
print("Order status:", order.status)
print("Order unchanged:", before == (order.payment_status, order.status))
