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
    "amount_gross": "358.00",
    "payment_status": "PENDING",
    "item_name": "Local ITN test",
    "item_description": "",
}

fields = []
for key, value in data.items():
    if value is not None:
        fields.append((key, str(value).strip()))

parameter_string = "&".join(
    f"{key}={quote_plus(value, safe='')}"
    for key, value in fields
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
print("Payment status before:", before[0])
print("Payment status after:", order.payment_status)
print("Order status before:", before[1])
print("Order status after:", order.status)
print(
    "Order unchanged:",
    before == (order.payment_status, order.status),
)
