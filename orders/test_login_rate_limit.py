from django.test import TestCase, override_settings
from django.urls import reverse

from axes.models import AccessAttempt


@override_settings(
    AXES_FAILURE_LIMIT=5,
    AXES_COOLOFF_TIME=0.25,
    AXES_ENABLED=True,
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    },
)
class LoginRateLimitTests(TestCase):
    """Verify failed-login protection on all four login portals."""

    def test_all_login_portals_lock_after_five_failed_attempts(self):
        login_routes = [
            ("customer_login", "rate_customer_test"),
            ("driver_login", "rate_driver_test"),
            ("staff_login", "rate_staff_test"),
            ("owner_login", "rate_owner_test"),
        ]

        for index, (route_name, username) in enumerate(login_routes):
            with self.subTest(portal=route_name):
                self.client.cookies.clear()
                test_ip = f"127.0.0.{index + 1}"

                url = reverse(route_name)

                for attempt in range(1, 5):
                    response = self.client.post(
                        url,
                        {
                            "username": username,
                            "password": "DefinitelyWrongPassword123!",
                        },
                        REMOTE_ADDR=test_ip,
                    )

                    self.assertEqual(
                        response.status_code,
                        200,
                        f"{route_name}: attempt {attempt} "
                        "should display the login page.",
                    )

                fifth_response = self.client.post(
                    url,
                    {
                        "username": username,
                        "password": "DefinitelyWrongPassword123!",
                    },
                    REMOTE_ADDR=test_ip,
                )

                self.assertEqual(
                    fifth_response.status_code,
                    429,
                    f"{route_name}: fifth failed attempt "
                    "should trigger HTTP 429.",
                )

                attempt_record = AccessAttempt.objects.filter(
                    username=username,
                    ip_address=test_ip,
                ).first()

                self.assertIsNotNone(
                    attempt_record,
                    f"{route_name}: Axes should record failed attempts.",
                )

                self.assertEqual(
                    attempt_record.failures_since_start,
                    5,
                    f"{route_name}: expected five recorded failures.",
                )
