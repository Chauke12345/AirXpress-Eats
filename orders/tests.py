
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


from django.test import SimpleTestCase
from unittest.mock import Mock
from django.utils import timezone
from datetime import timedelta

from orders.views import (
    _delivery_otp_hash,
    _verify_delivery_otp,
)


class DeliveryOTPHelperTests(SimpleTestCase):
    """Tests for delivery OTP verification without sending SMS."""

    def setUp(self):
        self.order = Mock()
        self.order.id = 123
        self.order.delivery_otp_hash = _delivery_otp_hash(
            self.order.id, "123456"
        )
        self.order.delivery_otp_expires_at = (
            timezone.now() + timedelta(minutes=10)
        )
        self.order.delivery_otp_attempts = 0
        self.order.delivery_otp_verified_at = None

    def test_correct_code_is_verified(self):
        valid, message = _verify_delivery_otp(
            self.order, "123456"
        )

        self.assertTrue(valid)
        self.assertEqual(
            message, "Customer delivery code verified."
        )
        self.assertIsNotNone(
            self.order.delivery_otp_verified_at
        )

    def test_incorrect_code_is_rejected(self):
        valid, message = _verify_delivery_otp(
            self.order, "999999"
        )

        self.assertFalse(valid)
        self.assertEqual(message, "Incorrect delivery code.")
        self.assertEqual(self.order.delivery_otp_attempts, 1)

    def test_expired_code_is_rejected(self):
        self.order.delivery_otp_expires_at = (
            timezone.now() - timedelta(minutes=1)
        )

        valid, message = _verify_delivery_otp(
            self.order, "123456"
        )

        self.assertFalse(valid)
        self.assertEqual(
            message,
            "The delivery code has expired. A new code is required.",
        )

    def test_five_attempt_limit_is_enforced(self):
        self.order.delivery_otp_attempts = 5

        valid, message = _verify_delivery_otp(
            self.order, "123456"
        )

        self.assertFalse(valid)
        self.assertEqual(
            message,
            "Too many incorrect attempts. A new code is required.",
        )


from django.test import override_settings
from orders.services import send_delivery_otp_sms


class DeliveryOTPSMSTests(SimpleTestCase):
    """Verify SMS safety without contacting a real SMS provider."""

    @override_settings(SMS_ENABLED=False, SMS_PROVIDER="console")
    def test_disabled_sms_does_not_send_message(self):
        result = send_delivery_otp_sms(
            "27000000000", "123456", 999
        )

        self.assertEqual(
            result,
            (False, "SMS sending is disabled. No SMS was sent."),
        )

    @override_settings(SMS_ENABLED=True, SMS_PROVIDER="console")
    def test_console_mode_does_not_send_real_sms(self):
        result = send_delivery_otp_sms(
            "27000000000", "123456", 999
        )

        self.assertEqual(
            result,
            (False, "Console mode does not send real SMS messages."),
        )

    @override_settings(SMS_ENABLED=True, SMS_PROVIDER="unconfigured")
    def test_unconfigured_provider_does_not_send_message(self):
        result = send_delivery_otp_sms(
            "27000000000", "123456", 999
        )

        self.assertEqual(
            result,
            (False, "SMS provider integration has not been configured."),
        )

    @override_settings(SMS_ENABLED=True, SMS_PROVIDER="console")
    def test_missing_phone_number_is_rejected(self):
        result = send_delivery_otp_sms("", "123456", 999)

        self.assertEqual(
            result,
            (False, "Customer phone number is missing."),
        )
