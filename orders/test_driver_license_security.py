import tempfile

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from orders.models import Driver
from orders.security import (
    MAX_DRIVER_LICENSE_SIZE,
    validate_driver_license_file,
)

User = get_user_model()


class DriverLicenseSecurityTests(TestCase):
    def setUp(self):
        self.temp_media = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_media.cleanup)

        self.media_override = override_settings(
            MEDIA_ROOT=self.temp_media.name
        )
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)

        self.customer = User.objects.create_user(
            username="license_security_customer",
            password="TestPassword!2026",
        )

        self.driver_user = User.objects.create_user(
            username="license_security_driver",
            password="TestPassword!2026",
        )

        self.other_driver_user = User.objects.create_user(
            username="license_security_other_driver",
            password="TestPassword!2026",
        )

        self.driver = Driver.objects.create(
            user=self.driver_user,
            name="Security Test Driver",
        )

        self.other_driver = Driver.objects.create(
            user=self.other_driver_user,
            name="Other Security Test Driver",
        )

        self.owner = User.objects.create_superuser(
            username="license_security_owner",
            email="license_security_owner@example.com",
            password="TestPassword!2026",
        )

        self.driver.driver_license.save(
            "security-test.pdf",
            ContentFile(b"%PDF-1.4\nSecurity test document"),
            save=True,
        )

    def test_driver_can_view_own_license(self):
        self.client.force_login(self.driver_user)

        response = self.client.get(
            reverse(
                "driver_view_license",
                kwargs={"driver_id": self.driver.pk},
            )
        )

        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_driver_cannot_view_another_drivers_license(self):
        self.client.force_login(self.other_driver_user)

        response = self.client.get(
            reverse(
                "driver_view_license",
                kwargs={"driver_id": self.driver.pk},
            )
        )

        self.assertEqual(response.status_code, 403)

    def test_customer_cannot_view_driver_license(self):
        self.client.force_login(self.customer)

        response = self.client.get(
            reverse(
                "driver_view_license",
                kwargs={"driver_id": self.driver.pk},
            )
        )

        self.assertEqual(response.status_code, 403)

    def test_logged_out_visitor_is_redirected(self):
        response = self.client.get(
            reverse(
                "driver_view_license",
                kwargs={"driver_id": self.driver.pk},
            )
        )

        self.assertEqual(response.status_code, 302)

    def test_owner_can_view_driver_license(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse(
                "driver_view_license",
                kwargs={"driver_id": self.driver.pk},
            )
        )

        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_direct_public_license_media_url_returns_404(self):
        response = self.client.get(
            "/media/driver_licenses/security-test.pdf"
        )

        self.assertEqual(response.status_code, 404)

    def test_fake_pdf_is_rejected(self):
        uploaded = SimpleUploadedFile(
            "fake.pdf",
            b"This is not a PDF document",
        )

        with self.assertRaises(ValidationError):
            validate_driver_license_file(uploaded)

    def test_unsupported_file_extension_is_rejected(self):
        uploaded = SimpleUploadedFile(
            "malicious.exe",
            b"MZ fake executable",
        )

        with self.assertRaises(ValidationError):
            validate_driver_license_file(uploaded)

    def test_oversized_license_is_rejected(self):
        uploaded = SimpleUploadedFile(
            "large.pdf",
            b"%PDF-" + (b"A" * MAX_DRIVER_LICENSE_SIZE),
        )

        with self.assertRaises(ValidationError):
            validate_driver_license_file(uploaded)

    def test_invalid_upload_does_not_replace_existing_license(self):
        self.driver.license_verification_status = "verified"
        self.driver.airxpress_verified = True
        self.driver.save()

        self.client.force_login(self.driver_user)

        invalid_upload = SimpleUploadedFile(
            "fake.pdf",
            b"This is not a PDF document",
        )

        response = self.client.post(
            reverse("driver_upload_license"),
            {"driver_license": invalid_upload},
        )

        self.driver.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.driver.driver_license.name,
            "driver_licenses/security-test.pdf",
        )
        self.assertEqual(
            self.driver.license_verification_status,
            "verified",
        )
        self.assertTrue(self.driver.airxpress_verified)
