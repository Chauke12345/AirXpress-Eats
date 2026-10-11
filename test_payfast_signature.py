import os
import django
import hashlib
from urllib.parse import quote_plus

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings
from orders.payfast import validate_itn_signature

data = {
    "m_payment_id": "TEST123",
    "pf_payment_id": "987654",
    "payment_status": "COMPLETE",
    "item_name": "Test Order",
    "item_description": "",
    "merchant_id": "10000100",
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

print("Valid test signature accepted:", validate_itn_signature(data))

data["payment_status"] = "CANCELLED"
print("Modified notification rejected:", not validate_itn_signature(data))
