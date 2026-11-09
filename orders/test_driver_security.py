from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from orders.models import Driver
from orders.security import is_driver

User = get_user_model()


class DriverAccessSecurityTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="security_customer",
            password="TestPassword!2026",
        )

        self.driver_user = User.objects.create_user(
            username="security_driver",
            password="TestPassword!2026",
        )

        self.driver = Driver.objects.create(
            user=self.driver_user,
            name="Security Test Driver",
            driver_license="driver_licenses/security-test.pdf",
        )

        self.owner = User.objects.create_superuser(
            username="security_owner",
            email="security_owner@example.com",
            password="TestPassword!2026",
        )

    def test_customer_is_not_recognised_as_driver(self):
        self.assertFalse(is_driver(self.customer))

    def test_driver_profile_is_recognised(self):
        self.assertTrue(is_driver(self.driver_user))

    def test_logged_out_visitor_cannot_access_driver_dashboard(self):
        response = self.client.get(reverse("driver_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/driver/login/"))

    def test_customer_cannot_access_driver_dashboard(self):
        self.client.force_login(self.customer)

        response = self.client.get(reverse("driver_dashboard"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/driver/login/"))

    def test_customer_cannot_upload_driver_licence(self):
        self.client.force_login(self.customer)

        response = self.client.post(
            reverse("driver_upload_license"),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/driver/login/"))

    def test_customer_cannot_verify_driver(self):
        self.client.force_login(self.customer)

        response = self.client.post(
            reverse(
                "owner_verify_driver",
                kwargs={"driver_id": self.driver.pk},
            ),
            {"action": "verify"},
        )

        self.driver.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/owner/login/"))
        self.assertEqual(
            self.driver.license_verification_status,
            "pending",
        )
        self.assertFalse(self.driver.airxpress_verified)

    def test_superuser_can_verify_driver(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse(
                "owner_verify_driver",
                kwargs={"driver_id": self.driver.pk},
            ),
            {"action": "verify"},
        )

        self.driver.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.driver.license_verification_status,
            "verified",
        )
        self.assertTrue(self.driver.airxpress_verified)
