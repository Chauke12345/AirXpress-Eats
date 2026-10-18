from django.shortcuts import redirect


class CustomerPasswordChangeMiddleware:
    """
    Require customers flagged for a password change to change it
    before accessing other pages.
    """

    EXEMPT_PATHS = (
        "/customer/change-password/",
        "/customer/logout/",
        "/static/",
        "/media/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user

        if user.is_authenticated and not user.is_staff and not user.is_superuser:
            if any(
                request.path.startswith(path)
                for path in self.EXEMPT_PATHS
            ):
                return self.get_response(request)

            try:
                profile = user.customer_profile
            except Exception:
                profile = None

            if profile and profile.must_change_password:
                return redirect("customer_change_password")

        return self.get_response(request)

class CustomerInactivityTimeoutMiddleware:
    """Enforce a 10-minute inactivity limit for authenticated customers."""

    TIMEOUT_SECONDS = 10 * 60
    WARNING_SECONDS = 8 * 60
    LAST_ACTIVITY_KEY = "airxpress_customer_last_activity"

    EXEMPT_PATHS = (
        "/customer/login/",
        "/customer/logout/",
        "/payment/payfast/",
        "/static/",
        "/media/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        import time
        from django.contrib.auth import logout
        from django.shortcuts import redirect

        user = getattr(request, "user", None)
        path = request.path

        if (
            user is None
            or not user.is_authenticated
            or user.is_staff
            or user.is_superuser
            or any(path.startswith(item) for item in self.EXEMPT_PATHS)
        ):
            return self.get_response(request)

        try:
            is_customer = user.customer_profile is not None
        except Exception:
            is_customer = False

        if not is_customer:
            return self.get_response(request)

        now = int(time.time())
        last_activity = request.session.get(self.LAST_ACTIVITY_KEY)

        if last_activity is None:
            request.session[self.LAST_ACTIVITY_KEY] = now
            request.session.set_expiry(self.TIMEOUT_SECONDS)
            request.inactivity_seconds = 0
            request.inactivity_warning = False
        else:
            try:
                inactive_for = max(0, now - int(last_activity))
            except (TypeError, ValueError):
                inactive_for = 0
                request.session[self.LAST_ACTIVITY_KEY] = now

            if inactive_for >= self.TIMEOUT_SECONDS:
                logout(request)
                request.session.flush()
                return redirect("customer_login")

            request.inactivity_seconds = inactive_for
            request.inactivity_warning = inactive_for >= self.WARNING_SECONDS

        return self.get_response(request)
