from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .turnstile import TurnstileError


User = get_user_model()


class CustomerRegistrationSecurityTests(TestCase):

    def setUp(self):
        self.url = reverse("customer_register")

        self.registration_data = {
            "full_name": "Security Test Customer",
            "username": "turnstile_test_customer",
            "email": "turnstile.test@example.com",
            "whatsapp_number": "0712345678",
            "password1": "AirXpress!Test2026Strong",
            "password2": "AirXpress!Test2026Strong",
            "accept_terms": "on",
        }

    def test_missing_token_prevents_account_creation(self):
        response = self.client.post(
            self.url,
            self.registration_data,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            User.objects.filter(
                username=self.registration_data["username"]
            ).exists()
        )

    @patch(
        "orders.views.verify_turnstile_token",
        side_effect=TurnstileError("Human verification failed."),
    )
    def test_failed_verification_prevents_account_creation(
        self,
        mock_verify,
    ):
        data = {
            **self.registration_data,
            "cf-turnstile-response": "invalid-test-token",
        }

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            User.objects.filter(
                username=self.registration_data["username"]
            ).exists()
        )
        mock_verify.assert_called_once_with(
            "invalid-test-token",
            "testserver",
        )

    @patch(
        "orders.views.verify_turnstile_token",
        return_value=True,
    )
    def test_successful_verification_creates_account(
        self,
        mock_verify,
    ):
        data = {
            **self.registration_data,
            "cf-turnstile-response": "valid-test-token",
        }

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("home"))

        user = User.objects.get(
            username=self.registration_data["username"]
        )

        self.assertEqual(
            user.email,
            self.registration_data["email"],
        )
        self.assertTrue(user.is_authenticated)
        self.assertTrue(
            self.client.session.get("_auth_user_id")
        )

        mock_verify.assert_called_once_with(
            "valid-test-token",
            "testserver",
        )

    @patch(
        "orders.views.verify_turnstile_token",
        side_effect=TurnstileError(
            "Human verification is temporarily unavailable."
        ),
    )
    def test_cloudflare_unavailable_prevents_registration(
        self,
        mock_verify,
    ):
        data = {
            **self.registration_data,
            "cf-turnstile-response": "valid-test-token",
        }

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            User.objects.filter(
                username=self.registration_data["username"]
            ).exists()
        )
        mock_verify.assert_called_once()
