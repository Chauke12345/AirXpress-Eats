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
    """
    Apply inactivity expiry only to customer accounts and the
    platform administrator. Shop and driver sessions are exempt.
    """

    TIMEOUT_SECONDS = 30 * 60
    WARNING_SECONDS = 28 * 60

    CUSTOMER_KEY = "airxpress_customer_last_activity"
    ADMIN_KEY = "airxpress_admin_last_activity"

    EXEMPT_PATHS = (
        "/customer/login/",
        "/customer/logout/",
        "/owner/login/",
        "/owner/logout/",
        "/payment/payfast/",
        "/static/",
        "/media/",
        "/track/",  # Tracking requests do not refresh customer activity.
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
            or any(path.startswith(item) for item in self.EXEMPT_PATHS)
        ):
            return self.get_response(request)

        # Platform administrator has a separate protected session.
        if user.is_superuser:
            activity_key = self.ADMIN_KEY
            login_url = "/owner/login/"

        else:
            # Drivers and all shop accounts control their own sessions.
            try:
                user.driver_profile
                return self.get_response(request)
            except Exception:
                pass

            try:
                user.staff_profile
                return self.get_response(request)
            except Exception:
                pass

            # Ordinary Django staff accounts are not customer accounts.
            if user.is_staff:
                return self.get_response(request)

            try:
                user.customer_profile
            except Exception:
                return self.get_response(request)

            activity_key = self.CUSTOMER_KEY
            login_url = "/customer/login/"

        now = int(time.time())
        last_activity = request.session.get(activity_key)
        inactive_for = 0

        if last_activity is not None:
            try:
                inactive_for = max(0, now - int(last_activity))
            except (TypeError, ValueError):
                inactive_for = 0

            if inactive_for >= self.TIMEOUT_SECONDS:
                logout(request)
                return redirect(login_url)

        # Refresh activity and the server-side session expiry.
        request.session[activity_key] = now
        request.session.set_expiry(self.TIMEOUT_SECONDS)

        request.inactivity_seconds = inactive_for
        request.inactivity_warning = (
            inactive_for >= self.WARNING_SECONDS
        )

        return self.get_response(request)
