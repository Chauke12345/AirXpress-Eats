
import hashlib
from decimal import Decimal
from urllib.parse import quote_plus
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from orders.models import Order, OrderStatusHistory, Shop


@override_settings(
    PAYFAST_MERCHANT_ID="test-merchant",
    PAYFAST_PASSPHRASE="test-passphrase",
    PAYFAST_SANDBOX=True,
)
class PayFastITNTests(TestCase):
    """Automated PayFast ITN tests using Django's test database."""

    def setUp(self):
        self.shop = Shop.objects.create(
            name="Automated Test Shop",
            slug="automated-test-shop",
            phone_number="0100000000",
            whatsapp_number="27010000000",
        )

        self.order = Order.objects.create(
            shop=self.shop,
            customer_name="Automated Test Customer",
            order_type="delivery",
            status="new",
            final_total=Decimal("358.00"),
            payment_status="pending",
        )

        self.itn_url = reverse("payfast_itn")

    def make_itn(self, **overrides):
        """Build a signed test notification without contacting PayFast."""
        data = {
            "m_payment_id": str(self.order.pk),
            "merchant_id": settings.PAYFAST_MERCHANT_ID,
            "amount_gross": "358.00",
            "payment_status": "COMPLETE",
            "item_name": "Automated test order",
            "item_description": "",
        }
        data.update(overrides)

        parameter_string = "&".join(
            f"{key}={quote_plus(str(value).strip(), safe='')}"
            for key, value in data.items()
            if value is not None
        )

        passphrase = (settings.PAYFAST_PASSPHRASE or "").strip()
        if passphrase:
            parameter_string += (
                "&passphrase=" + quote_plus(passphrase, safe="")
            )

        data["signature"] = hashlib.md5(
            parameter_string.encode("utf-8")
        ).hexdigest()

        return data

    @patch("orders.payfast.validate_itn_with_payfast", return_value=True)
    def test_valid_payment_marks_order_paid(self, mock_validation):
        response = self.client.post(
            self.itn_url,
            self.make_itn(),
        )

        self.order.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.order.payment_status, "paid")
        self.assertTrue(
            OrderStatusHistory.objects.filter(
                order=self.order,
                notes__contains="PayFast payment confirmed",
            ).exists()
        )
        mock_validation.assert_called_once()

    @patch("orders.payfast.validate_itn_with_payfast", return_value=True)
    def test_invalid_signature_is_rejected(self, mock_validation):
        data = self.make_itn()
        data["signature"] = "invalid-signature"

        response = self.client.post(self.itn_url, data)

        self.order.refresh_from_db()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["status"],
            "invalid_signature",
        )
        self.assertEqual(self.order.payment_status, "pending")
        mock_validation.assert_not_called()

    @patch("orders.payfast.validate_itn_with_payfast", return_value=True)
    def test_incorrect_amount_is_rejected(self, mock_validation):
        response = self.client.post(
            self.itn_url,
            self.make_itn(amount_gross="1.00"),
        )

        self.order.refresh_from_db()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "amount_mismatch")
        self.assertEqual(self.order.payment_status, "pending")
        mock_validation.assert_called_once()

    @patch("orders.payfast.validate_itn_with_payfast", return_value=True)
    def test_wrong_merchant_is_rejected(self, mock_validation):
        response = self.client.post(
            self.itn_url,
            self.make_itn(merchant_id="wrong-merchant"),
        )

        self.order.refresh_from_db()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "merchant_mismatch")
        self.assertEqual(self.order.payment_status, "pending")
        mock_validation.assert_called_once()

    @patch("orders.payfast.validate_itn_with_payfast", return_value=True)
    def test_pending_payment_does_not_mark_order_paid(self, mock_validation):
        response = self.client.post(
            self.itn_url,
            self.make_itn(payment_status="PENDING"),
        )

        self.order.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["status"],
            "payment_not_complete",
        )
        self.assertEqual(self.order.payment_status, "pending")
        mock_validation.assert_called_once()
