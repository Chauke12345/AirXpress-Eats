from django.urls import path
from django.contrib.auth import views as auth_views

from . import views


urlpatterns = [

    # =========================================================
    # MAPBOX ADDRESS SUGGESTIONS
    # =========================================================

    path(
        "address-suggestions/",
        views.address_suggestions,
        name="address_suggestions",
    ),


    # =========================================================
    # PUBLIC PLATFORM HOMEPAGE
    # =========================================================

    path(
        "",
        views.home,
        name="home",
    ),

    # =========================================================
    # CUSTOMER
    path("customer/banking/", views.customer_banking_details, name="customer_banking_details"),

    # =========================================================
    path(
        "shop/<slug:shop_slug>/cart/add/<int:menu_item_id>/",
        views.add_to_cart,
        name="add_to_cart",
    ),

    path(
        "customer/register/",
        views.customer_register,
        name="customer_register",
    ),

    path(
        "customer/login/",
        views.customer_login,
        name="customer_login",
    ),

    path(
        "customer/logout/",
        auth_views.LogoutView.as_view(
            next_page="home",
        ),
        name="customer_logout",
    ),

    path(
        "customer/password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="orders/customer_password_reset.html",
            email_template_name="orders/customer_password_reset_email.txt",
            subject_template_name="orders/customer_password_reset_subject.txt",
            success_url="/customer/password-reset/done/",
        ),
        name="customer_password_reset",
    ),

    path(
        "customer/password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="orders/customer_password_reset_done.html",
        ),
        name="customer_password_reset_done",
    ),

    path(
        "customer/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="orders/customer_password_reset_confirm.html",
            success_url="/customer/reset/done/",
        ),
        name="customer_password_reset_confirm",
    ),

    path(
        "customer/reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="orders/customer_password_reset_complete.html",
        ),
        name="customer_password_reset_complete",
    ),

    path(
        "shop/<slug:shop_slug>/cart/update/<int:menu_item_id>/",
        views.update_cart,
        name="update_cart",
    ),

    path(
        "shop/<slug:shop_slug>/cart/remove/<int:menu_item_id>/",
        views.remove_from_cart,
        name="remove_from_cart",
    ),
    path(
        "shop/<slug:shop_slug>/cart/",
        views.cart,
        name="cart",
    ),    path(
        "shop/<slug:shop_slug>/checkout/",
        views.checkout,
        name="checkout",
    ),

    path(
        "shop/<slug:shop_slug>/",
        views.customer_order,
        name="customer_order",
    ),

    path(
        "shop/<slug:shop_slug>/orders/",
        views.customer_order_history,
        name="customer_order_history",
    ),
    path(
        "shop/<slug:shop_slug>/order/<int:order_id>/invoice/",
        views.customer_invoice,
        name="customer_invoice",
    ),


    path(
        "shop/<slug:shop_slug>/order/<int:order_id>/success/",
        views.order_success,
        name="order_success",
    ),
    path(
        "customer/my-orders/",
        views.customer_my_orders,
        name="customer_my_orders",
    ),
    path(
        "customer/orders/<int:order_id>/review/",
        views.order_review,
        name="order_review",
    ),
    path(
        "track/<uuid:tracking_token>/",
        views.track_order,
        name="track_order",
    ),
    path(
        "track/<uuid:tracking_token>/status/",
        views.track_order_status,
        name="track_order_status",
    ),
    path(
        "driver/orders/<int:order_id>/location/",
        views.update_driver_location,
        name="update_driver_location",
    ),


    # =========================================================
    # PAYFAST PAYMENT
    # =========================================================

    path(
        "payment/payfast/<int:order_id>/",
        views.payfast_payment,
        name="payfast_payment",
    ),
    # =========================================================
    # =========================================================
    # PAYFAST ITN
    # =========================================================

    path(
        "payment/payfast/itn/",
        views.payfast_itn,
        name="payfast_itn",
    ),
    # DRIVER LOGIN / LOGOUT
    # =========================================================

    path(
        "driver/login/",
        views.driver_login,
        name="driver_login",
    ),

    path(
    "driver/logout/",
    auth_views.LogoutView.as_view(
        next_page="driver_login",
    ),
    name="driver_logout",
),
    path(
    "customer/login/",
    views.customer_login,
    name="customer_login",
),

    # =========================================================
    # DRIVER
    # =========================================================

    path(
        "driver/dashboard/",
        views.driver_dashboard,
        name="driver_dashboard",
    ),

    path(
        "driver/banking/update/",
        views.driver_update_banking,
        name="driver_update_banking",
    ),
    path(
        "driver/profile/update/",
        views.driver_update_profile,
        name="driver_update_profile",
    ),
    path(
        "driver/profile/license-upload/",
        views.driver_upload_license,
        name="driver_upload_license",
    ),


    path(
        "driver/request/<int:request_id>/accept/",
        views.driver_accept_request,
        name="driver_accept_request",
    ),

    path(
        "driver/request/<int:request_id>/decline/",
        views.driver_decline_request,
        name="driver_decline_request",
    ),

    path(
        "driver/order/<int:order_id>/pickup/",
        views.driver_pickup_order,
        name="driver_pickup_order",
    ),

    path(
        "driver/order/<int:order_id>/deliver/",
        views.driver_deliver_order,
        name="driver_deliver_order",
    ),

    path(
        "driver/order/<int:order_id>/complete/",
        views.driver_complete_delivery,
        name="driver_complete_delivery",
    ),


    # =========================================================
    # STAFF LOGIN / LOGOUT
    # =========================================================

    path(
        "staff/login/",
        views.staff_login,
        name="staff_login",
    ),

    path(
        "staff/logout/",
        auth_views.LogoutView.as_view(
            next_page="staff_login"
        ),
        name="staff_logout",
    ),

# =========================================================
# STAFF
# =========================================================

path(
    "staff/dashboard/",
    views.staff_dashboard,
    name="staff_dashboard",
),

path(
    "staff/dashboard/updates/",
    views.staff_dashboard_updates,
    name="staff_dashboard_updates",
),
path("staff/order/<int:order_id>/update/",
    views.staff_update_order,
    name="staff_update_order",
),
  path(
      "staff/notify-drivers/<int:order_id>/",
      views.staff_notify_drivers,
      name="staff_notify_drivers",
  ),


path(
    "staff/history/",
    views.staff_order_history,
    name="staff_order_history",
),

path(
    "staff/reports/daily/",
    views.staff_daily_report,
    name="staff_daily_report",
),

    # =========================================================
    # MANAGEMENT LOGIN / LOGOUT
    # =========================================================

    path(
        "owner/login/",
        views.owner_login,
        name="owner_login",
    ),

    path(
        "owner/logout/",
        auth_views.LogoutView.as_view(
            next_page="owner_login"
        ),
        name="owner_logout",
    ),


    # =========================================================
    # MANAGEMENT / OWNER
    # =========================================================

    path(
        "owner/dashboard/",
        views.owner_dashboard,
        name="owner_dashboard",
    ),

    path(
        "owner/driver/<int:driver_id>/verify/",
        views.owner_verify_driver,
        name="owner_verify_driver",
    ),

    path(
        "owner/mark-fees-paid/",
        views.mark_platform_fees_paid,
        name="mark_platform_fees_paid",
    ),


    path(
        "owner/driver-payouts/",
        views.owner_driver_payouts,
        name="owner_driver_payouts",
    ),

    path(
        "owner/driver-payout/<int:payout_id>/mark-paid/",
        views.mark_driver_payout_paid,
        name="mark_driver_payout_paid",
    ),]



























