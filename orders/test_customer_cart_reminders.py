from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from orders.models import CustomerCart, CustomerNotification, Order, Shop


class CustomerCartReminderTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.customer = User.objects.create_user(
            username="cart_reminder_customer",
            password="test-password-123",
        )
        self.shop = Shop.objects.create(
            name="Reminder Test Shop",
            slug="reminder-test-shop",
            phone_number="0100000000",
            whatsapp_number="27010000000",
        )
        self.cart = CustomerCart.objects.create(
            customer=self.customer,
            shop=self.shop,
            items={"item-1": {"name": "Test meal", "quantity": 1}},
            is_active=True,
        )

    def age_cart(self, hours):
        past = timezone.now() - timedelta(hours=hours)
        CustomerCart.objects.filter(pk=self.cart.pk).update(
            updated_at=past
        )
        self.cart.refresh_from_db()

    def run_reminder_command(self, fixed_now):
        with patch(
            "orders.management.commands.send_cart_reminders.timezone.now",
            return_value=fixed_now,
        ):
            call_command("send_cart_reminders", verbosity=0)

    def test_one_hour_reminder_is_sent_once(self):
        fixed_now = timezone.now()
        self.age_cart(2)

        self.run_reminder_command(fixed_now)

        self.cart.refresh_from_db()
        self.assertIsNotNone(self.cart.reminder_1_sent_at)
        self.assertEqual(
            CustomerNotification.objects.filter(
                customer=self.customer,
                notification_type="cart_reminder",
            ).count(),
            1,
        )

        self.run_reminder_command(fixed_now)

        self.assertEqual(
            CustomerNotification.objects.filter(
                customer=self.customer,
                notification_type="cart_reminder",
            ).count(),
            1,
        )

    def test_second_reminder_is_sent_after_24_hours(self):
        fixed_now = timezone.now()
        self.age_cart(25)

        self.cart.reminder_1_sent_at = fixed_now - timedelta(hours=24)
        self.cart.save(update_fields=["reminder_1_sent_at"])

        self.run_reminder_command(fixed_now)

        self.cart.refresh_from_db()
        self.assertIsNotNone(self.cart.reminder_2_sent_at)
        self.assertEqual(
            CustomerNotification.objects.filter(
                customer=self.customer,
                notification_type="cart_reminder",
            ).count(),
            1,
        )

    def test_cart_with_existing_order_does_not_receive_reminder(self):
        fixed_now = timezone.now()
        self.age_cart(2)

        Order.objects.create(
            shop=self.shop,
            customer_account=self.customer,
            customer_name="Test Customer",
            order_type="delivery",
        )

        self.run_reminder_command(fixed_now)

        self.cart.refresh_from_db()
        self.assertIsNone(self.cart.reminder_1_sent_at)
        self.assertEqual(
            CustomerNotification.objects.filter(
                customer=self.customer,
                notification_type="cart_reminder",
            ).count(),
            0,
        )

    def test_empty_cart_does_not_receive_reminder(self):
        fixed_now = timezone.now()
        self.age_cart(2)

        self.cart.items = {}
        self.cart.is_active = False
        self.cart.save(update_fields=["items", "is_active"])

        self.run_reminder_command(fixed_now)

        self.assertEqual(
            CustomerNotification.objects.filter(
                customer=self.customer,
                notification_type="cart_reminder",
            ).count(),
            0,
        )
