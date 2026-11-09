from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import TestCase
from django.urls import reverse

from orders.models import CustomerProfile


User = get_user_model()


class OwnerCustomerPasswordResetTests(TestCase):

    def setUp(self):
        self.owner = User.objects.create_superuser(
            username="reset_test_owner",
            email="reset-owner@example.com",
            password="Owner!Secure2026Pass",
        )

        self.customer = User.objects.create_user(
            username="reset_test_customer",
            password="Old!Customer2026Pass",
            first_name="Test Customer",
        )

        self.profile = CustomerProfile.objects.create(
            user=self.customer,
            must_change_password=False,
            whatsapp_number="0821234567",
        )

        self.url = reverse(
            "owner_reset_customer_password",
            kwargs={"customer_id": self.profile.id},
        )

    def generate_pending_password(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.url, {"action": "generate"})
        self.assertEqual(response.status_code, 200)
        return response

    def confirm_password(self, response, token=None, password=None):
        return self.client.post(
            self.url,
            {
                "action": "confirm",
                "confirmation_token": (
                    token or response.context["confirmation_token"]
                ),
                "temporary_password": (
                    password or response.context["temporary_password"]
                ),
            },
        )

    def test_generation_does_not_activate_temporary_password(self):
        response = self.generate_pending_password()

        self.customer.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertTemplateUsed(
            response,
            "orders/owner_customer_password_reset_result.html",
        )
        self.assertTrue(response.context["temporary_password"])
        self.assertTrue(
            self.customer.check_password("Old!Customer2026Pass")
        )
        self.assertFalse(
            self.customer.check_password(
                response.context["temporary_password"]
            )
        )
        self.assertFalse(self.profile.must_change_password)

        whatsapp_url = response.context["whatsapp_url"]
        self.assertIn("https://wa.me/27821234567?", whatsapp_url)

        message = parse_qs(urlsplit(whatsapp_url).query)["text"][0]
        self.assertIn(response.context["temporary_password"], message)
        self.assertIn("Test Customer", message)
        self.assertIn(response.context["customer_login_url"], message)
        self.assertIn("create a new password", message)

    def test_confirmation_activates_password_and_forces_change(self):
        response = self.generate_pending_password()
        temporary_password = response.context["temporary_password"]

        confirmation = self.confirm_password(response)

        self.customer.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertRedirects(
            confirmation,
            reverse("owner_dashboard"),
            fetch_redirect_response=False,
        )
        self.assertTrue(self.customer.check_password(temporary_password))
        self.assertFalse(
            self.customer.check_password("Old!Customer2026Pass")
        )
        self.assertTrue(self.profile.must_change_password)

    def test_confirmation_token_cannot_be_reused(self):
        response = self.generate_pending_password()

        first = self.confirm_password(response)
        second = self.confirm_password(response)

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)

        self.customer.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertTrue(
            self.customer.check_password(
                response.context["temporary_password"]
            )
        )
        self.assertTrue(self.profile.must_change_password)

    def test_modified_password_is_rejected(self):
        response = self.generate_pending_password()

        confirmation = self.confirm_password(
            response,
            password="AttackerChangedPassword!2026",
        )

        self.customer.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertEqual(confirmation.status_code, 302)
        self.assertTrue(
            self.customer.check_password("Old!Customer2026Pass")
        )
        self.assertFalse(self.profile.must_change_password)

    def test_expired_confirmation_token_is_rejected(self):
        response = self.generate_pending_password()

        with patch(
            "orders.views.signing.loads",
            side_effect=signing.SignatureExpired("Confirmation expired."),
        ):
            confirmation = self.confirm_password(response)

        self.customer.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertEqual(confirmation.status_code, 302)
        self.assertTrue(
            self.customer.check_password("Old!Customer2026Pass")
        )
        self.assertFalse(self.profile.must_change_password)

    def test_non_owner_cannot_reset_customer_password(self):
        staff = User.objects.create_user(
            username="reset_test_staff",
            password="Staff!Secure2026Pass",
            is_staff=True,
        )

        self.client.force_login(staff)
        response = self.client.post(self.url, {"action": "generate"})

        self.customer.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertIn("/owner/login/", response.url)
        self.assertTrue(
            self.customer.check_password("Old!Customer2026Pass")
        )
        self.assertFalse(self.profile.must_change_password)

    def test_missing_whatsapp_number_prevents_generation(self):
        self.profile.whatsapp_number = ""
        self.profile.save(update_fields=["whatsapp_number"])

        self.client.force_login(self.owner)
        response = self.client.post(self.url, {"action": "generate"})

        self.customer.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            self.customer.check_password("Old!Customer2026Pass")
        )
        self.assertFalse(self.profile.must_change_password)

    def test_invalid_whatsapp_number_prevents_generation(self):
        self.profile.whatsapp_number = "12345"
        self.profile.save(update_fields=["whatsapp_number"])

        self.client.force_login(self.owner)
        response = self.client.post(self.url, {"action": "generate"})

        self.customer.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            self.customer.check_password("Old!Customer2026Pass")
        )
        self.assertFalse(self.profile.must_change_password)

    def test_get_request_does_not_reset_password(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)

        self.customer.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            self.customer.check_password("Old!Customer2026Pass")
        )
        self.assertFalse(self.profile.must_change_password)
