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
