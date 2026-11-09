from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from orders.middleware import CustomerPasswordChangeMiddleware
from orders.models import CustomerProfile


User = get_user_model()


class CustomerPasswordChangeMiddlewareTests(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.customer = User.objects.create_user(
            username="temporary_password_customer",
            password="TestPassword!2026",
        )
        self.profile = CustomerProfile.objects.create(
            user=self.customer,
            must_change_password=True,
        )
        self.middleware = CustomerPasswordChangeMiddleware(
            lambda request: HttpResponse("Access granted")
        )

    def check_path(self, path, user):
        request = self.factory.get(path)
        request.user = user
        return self.middleware(request)

    def test_temporary_password_customer_is_redirected(self):
        response = self.check_path("/", self.customer)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("customer_change_password"),
        )

    def test_password_change_page_is_allowed(self):
        response = self.check_path(
            reverse("customer_change_password"),
            self.customer,
        )

        self.assertEqual(response.status_code, 200)

    def test_customer_logout_is_allowed(self):
        response = self.check_path(
            reverse("customer_logout"),
            self.customer,
        )

        self.assertEqual(response.status_code, 200)

    def test_customer_with_normal_password_can_access_pages(self):
        self.profile.must_change_password = False
        self.profile.save(update_fields=["must_change_password"])

        response = self.check_path("/", self.customer)

        self.assertEqual(response.status_code, 200)

    def test_staff_are_not_redirected(self):
        staff = User.objects.create_user(
            username="middleware_test_staff",
            password="TestPassword!2026",
            is_staff=True,
        )

        response = self.check_path("/", staff)

        self.assertEqual(response.status_code, 200)

    def test_owner_is_not_redirected(self):
        owner = User.objects.create_superuser(
            username="middleware_test_owner",
            email="owner-test@example.com",
            password="TestPassword!2026",
        )

        response = self.check_path("/", owner)

        self.assertEqual(response.status_code, 200)

    def test_non_customer_user_is_not_redirected(self):
        driver = User.objects.create_user(
            username="middleware_test_driver",
            password="TestPassword!2026",
        )

        response = self.check_path("/", driver)

        self.assertEqual(response.status_code, 200)
