from django.urls import reverse

from .models import CustomerNotification


STATUS_MESSAGES = {
    "new": (
        "Order received",
        "We have received your order #{order_id}.",
    ),
    "preparing": (
        "Your order is being prepared",
        "The shop has started preparing order #{order_id}.",
    ),
    "ready": (
        "Your order is ready",
        "Order #{order_id} is ready. Please check your order for collection or delivery updates.",
    ),
    "driver_assigned": (
        "Driver assigned",
        "A driver has been assigned to order #{order_id}.",
    ),
    "picked_up": (
        "Your order is on its way",
        "The driver has picked up order #{order_id}.",
    ),
    "delivered": (
        "Order delivered",
        "Order #{order_id} has been marked as delivered.",
    ),
    "collected": (
        "Order completed",
        "Order #{order_id} has been completed.",
    ),
    "cancelled": (
        "Order cancelled",
        "Order #{order_id} has been cancelled. Please contact the shop if you need assistance.",
    ),
}


def notify_customer_for_status_history(status_history):
    """
    Create one persistent customer notification for a genuine
    order-status event. Guest orders are intentionally skipped.
    """
    order = status_history.order
    customer = order.customer_account

    if not customer or not customer.is_active:
        return None

    notification_content = STATUS_MESSAGES.get(status_history.status)
    if not notification_content:
        return None

    title, message_template = notification_content

    notification, created = CustomerNotification.objects.get_or_create(
        status_history=status_history,
        defaults={
            "customer": customer,
            "order": order,
            "notification_type": "order_update",
            "title": title,
            "message": message_template.format(order_id=order.id),
            "target_url": reverse("customer_my_orders"),
        },
    )

    return notification if created else None
