from django.conf import settings


def send_delivery_otp_sms(phone_number, code, order_id):
    """
    Send a delivery OTP SMS.

    Current mode is test-only. No real SMS is sent until a provider
    is configured and explicitly enabled.
    """
    if not phone_number:
        return False, "Customer phone number is missing."

    if not settings.SMS_ENABLED:
        return False, "SMS sending is disabled. No SMS was sent."

    provider = getattr(settings, "SMS_PROVIDER", "console")

    if provider == "console":
        return False, "Console mode does not send real SMS messages."

    return False, "SMS provider integration has not been configured."
