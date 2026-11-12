import logging

import requests
from django.conf import settings


logger = logging.getLogger(__name__)

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TURNSTILE_TIMEOUT_SECONDS = 5
TURNSTILE_REGISTRATION_ACTION = "customer_registration"


class TurnstileError(Exception):
    """Raised when human verification cannot be completed."""


def verify_turnstile_token(token, expected_hostname, expected_action=None):
    """
    Verify a Cloudflare Turnstile token server-side.

    Cloudflare validates token expiry and single-use status.
    The hostname and action are checked independently.
    """

    secret_key = getattr(settings, "TURNSTILE_SECRET_KEY", "").strip()

    if not secret_key:
        raise TurnstileError("Human verification is not configured.")

    if not isinstance(token, str) or not token.strip():
        raise TurnstileError("Human verification is required.")

    if not expected_hostname:
        raise TurnstileError("Verification hostname is not configured.")

    payload = {
        "secret": secret_key,
        "response": token.strip(),
    }

    try:
        response = requests.post(
            TURNSTILE_VERIFY_URL,
            data=payload,
            timeout=TURNSTILE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        result = response.json()

    except requests.RequestException as exc:
        logger.warning(
            "Turnstile verification request failed: %s",
            type(exc).__name__,
        )
        raise TurnstileError(
            "Human verification is temporarily unavailable. Please try again."
        ) from exc

    except ValueError as exc:
        logger.warning("Turnstile returned an invalid JSON response.")
        raise TurnstileError(
            "Human verification could not be completed."
        ) from exc

    if not isinstance(result, dict):
        raise TurnstileError("Invalid human verification response.")

    if result.get("success") is not True:
        logger.warning(
            "Turnstile verification rejected: %s",
            result.get("error-codes", []),
        )
        raise TurnstileError("Human verification failed. Please try again.")

    actual_hostname = str(result.get("hostname", "")).strip().lower()
    expected_hostname = expected_hostname.strip().lower()

    if actual_hostname != expected_hostname:
        logger.warning("Turnstile hostname validation failed.")
        raise TurnstileError("Human verification failed.")

    if result.get("action") != (expected_action or TURNSTILE_REGISTRATION_ACTION):
        logger.warning("Turnstile action validation failed.")
        raise TurnstileError("Human verification failed.")

    return True
