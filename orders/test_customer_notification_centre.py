from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from orders.models import CustomerNotification


class CustomerNotificationCentreTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.customer = User.objects.create_user(
            username="notification_customer",
            password="test-password-123",
        )
        self.other_customer = User.objects.create_user(
            username="other_notification_customer",
            password="test-password-123",
        )

        self.notification = CustomerNotification.objects.create(
            customer=self.customer,
            notification_type="general",
            title="Test notification",
            message="This is a test notification.",
            target_url="/",
        )

        self.other_notification = CustomerNotification.objects.create(
            customer=self.other_customer,
            notification_type="general",
            title="Private notification",
            message="This belongs to another customer.",
            target_url="/",
        )

        # Bypass authentication backends during test setup.
        # These tests focus on notification access and ownership.
        self.client.force_login(self.customer)

    def test_customer_can_open_notification_centre(self):
        response = self.client.get(reverse("customer_notifications"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test notification")
        self.assertNotContains(response, "Private notification")

    def test_customer_can_mark_own_notification_as_read(self):
        url = reverse(
            "customer_notification_mark_read",
            kwargs={"notification_id": self.notification.pk},
        )

        response = self.client.post(url)

        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_read)
        self.assertIsNotNone(self.notification.read_at)
        self.assertEqual(response.status_code, 302)

    def test_customer_cannot_mark_another_customers_notification_as_read(self):
        url = reverse(
            "customer_notification_mark_read",
            kwargs={"notification_id": self.other_notification.pk},
        )

        response = self.client.post(url)

        self.other_notification.refresh_from_db()
        self.assertFalse(self.other_notification.is_read)
        self.assertEqual(response.status_code, 404)

    def test_mark_all_read_only_affects_logged_in_customer(self):
        url = reverse("customer_notifications_mark_all_read")

        response = self.client.post(url)

        self.notification.refresh_from_db()
        self.other_notification.refresh_from_db()

        self.assertTrue(self.notification.is_read)
        self.assertFalse(self.other_notification.is_read)
        self.assertEqual(response.status_code, 302)
