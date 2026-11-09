from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from .turnstile import (
    TURNSTILE_REGISTRATION_ACTION,
    TURNSTILE_VERIFY_URL,
    TurnstileError,
    verify_turnstile_token,
)


@override_settings(TURNSTILE_SECRET_KEY="test-secret-key")
class TurnstileVerificationTests(SimpleTestCase):

    HOSTNAME = "example.com"
    TOKEN = "valid-test-token"

    def cloudflare_response(self, **overrides):
        data = {
            "success": True,
            "hostname": self.HOSTNAME,
            "action": TURNSTILE_REGISTRATION_ACTION,
            "challenge_ts": "2026-11-09T08:00:00Z",
        }
        data.update(overrides)

        response = Mock()
        response.json.return_value = data
        response.raise_for_status.return_value = None
        return response

    @patch("orders.turnstile.requests.post")
    def test_valid_token_is_accepted(self, mock_post):
        mock_post.return_value = self.cloudflare_response()

        result = verify_turnstile_token(
            self.TOKEN,
            self.HOSTNAME,
        )

        self.assertTrue(result)
        mock_post.assert_called_once()

        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], TURNSTILE_VERIFY_URL)
        self.assertEqual(kwargs["data"]["secret"], "test-secret-key")
        self.assertEqual(kwargs["data"]["response"], self.TOKEN)
        self.assertEqual(kwargs["timeout"], 5)

    @patch("orders.turnstile.requests.post")
    def test_invalid_token_is_rejected(self, mock_post):
        mock_post.return_value = self.cloudflare_response(
            success=False,
            **{"error-codes": ["invalid-input-response"]},
        )

        with self.assertRaises(TurnstileError):
            verify_turnstile_token(self.TOKEN, self.HOSTNAME)

    @patch("orders.turnstile.requests.post")
    def test_expired_token_is_rejected(self, mock_post):
        mock_post.return_value = self.cloudflare_response(
            success=False,
            **{"error-codes": ["timeout-or-duplicate"]},
        )

        with self.assertRaises(TurnstileError):
            verify_turnstile_token(self.TOKEN, self.HOSTNAME)

    @patch("orders.turnstile.requests.post")
    def test_reused_token_is_rejected(self, mock_post):
        mock_post.return_value = self.cloudflare_response(
            success=False,
            **{"error-codes": ["timeout-or-duplicate"]},
        )

        with self.assertRaises(TurnstileError):
            verify_turnstile_token(self.TOKEN, self.HOSTNAME)

    @patch("orders.turnstile.requests.post")
    def test_wrong_hostname_is_rejected(self, mock_post):
        mock_post.return_value = self.cloudflare_response(
            hostname="attacker.example",
        )

        with self.assertRaises(TurnstileError):
            verify_turnstile_token(self.TOKEN, self.HOSTNAME)

    @patch("orders.turnstile.requests.post")
    def test_wrong_action_is_rejected(self, mock_post):
        mock_post.return_value = self.cloudflare_response(
            action="login",
        )

        with self.assertRaises(TurnstileError):
            verify_turnstile_token(self.TOKEN, self.HOSTNAME)

    @override_settings(TURNSTILE_SECRET_KEY="")
    def test_missing_secret_is_rejected(self):
        with self.assertRaises(TurnstileError):
            verify_turnstile_token(self.TOKEN, self.HOSTNAME)

    @patch("orders.turnstile.requests.post")
    def test_empty_token_is_rejected(self, mock_post):
        with self.assertRaises(TurnstileError):
            verify_turnstile_token("", self.HOSTNAME)

        mock_post.assert_not_called()

    @patch(
        "orders.turnstile.requests.post",
        side_effect=requests.Timeout,
    )
    def test_cloudflare_timeout_fails_closed(self, mock_post):
        with self.assertRaises(TurnstileError):
            verify_turnstile_token(self.TOKEN, self.HOSTNAME)

    @patch("orders.turnstile.requests.post")
    def test_invalid_json_response_is_rejected(self, mock_post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = ValueError("Invalid JSON")
        mock_post.return_value = response

        with self.assertRaises(TurnstileError):
            verify_turnstile_token(self.TOKEN, self.HOSTNAME)

    @patch("orders.turnstile.requests.post")
    def test_non_dictionary_response_is_rejected(self, mock_post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = []
        mock_post.return_value = response

        with self.assertRaises(TurnstileError):
            verify_turnstile_token(self.TOKEN, self.HOSTNAME)
