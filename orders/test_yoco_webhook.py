import base64
import hashlib
import hmac
import json
import time

from decimal import Decimal
from django.test import TestCase, override_settings
from django.urls import reverse

from orders.models import Order, Shop


TEST_SECRET = "whsec_" + base64.b64encode(
    b"temporary-yoco-test-secret"
).decode()


@override_settings(YOCO_WEBHOOK_SECRET=TEST_SECRET)
class YocoSuccessfulWebhookTest(TestCase):

    def setUp(self):
        self.shop = Shop.objects.create(
            name="Temporary Yoco Test Shop",
            phone_number="+27000000000",
            whatsapp_number="+27000000000",
        )

        self.order = Order.objects.create(
            shop=self.shop,
            customer_name="Yoco Test Customer",
            order_type="delivery",
            final_total=Decimal("125.00"),
            payment_provider="yoco",
            payment_reference="ch_test_airxpress_001",
        )

    def test_successful_payment_and_duplicate_notification(self):
        event = {
            "id": "evt_test_airxpress_001",
            "type": "payment.succeeded",
            "payload": {
                "id": "pay_test_airxpress_001",
                "amount": 12500,
                "currency": "ZAR",
                "status": "succeeded",
                "metadata": {
                    "checkoutId": "ch_test_airxpress_001"
                },
            },
        }

        body = json.dumps(event).encode("utf-8")
        webhook_id = "msg_test_airxpress_001"
        timestamp = str(int(time.time()))

        signed_content = (
            webhook_id + "." + timestamp + "."
        ).encode("utf-8") + body

        secret_bytes = base64.b64decode(TEST_SECRET[len("whsec_"):])

        signature = base64.b64encode(
            hmac.new(
                secret_bytes,
                signed_content,
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        headers = {
            "HTTP_WEBHOOK_ID": webhook_id,
            "HTTP_WEBHOOK_TIMESTAMP": timestamp,
            "HTTP_WEBHOOK_SIGNATURE": "v1," + signature,
        }

        url = reverse("yoco_webhook")

        first_response = self.client.post(
            url,
            data=body,
            content_type="application/json",
            **headers,
        )

        self.assertEqual(first_response.status_code, 200)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")
        self.assertIsNotNone(self.order.payment_paid_at)

        first_paid_at = self.order.payment_paid_at

        second_response = self.client.post(
            url,
            data=body,
            content_type="application/json",
            **headers,
        )

        self.assertEqual(second_response.status_code, 200)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")
        self.assertEqual(self.order.payment_paid_at, first_paid_at)
