from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from orders.models import CustomerCart, CustomerNotification, Order
from orders.push_notifications import send_customer_push_notification


class Command(BaseCommand):
    help = "Send one-hour and 24-hour abandoned-cart reminders."

    def handle(self, *args, **options):
        now = timezone.now()
        sent_first = 0
        sent_second = 0
        skipped_orders = 0

        candidates = (
            CustomerCart.objects
            .filter(is_active=True)
            .exclude(items={})
            .select_related("customer", "shop")
            .order_by("updated_at")
        )

        for candidate in candidates.iterator():
            with transaction.atomic():
                try:
                    cart = (
                        CustomerCart.objects
                        .select_for_update()
                        .select_related("customer", "shop")
                        .get(pk=candidate.pk)
                    )
                except CustomerCart.DoesNotExist:
                    continue

                if not cart.is_active or not cart.items:
                    continue

                if not cart.customer.is_active or not cart.shop.is_active:
                    continue

                # Do not remind a customer who has already placed an order
                # for this shop since the cart was last changed.
                order_exists = Order.objects.filter(
                    customer_account=cart.customer,
                    shop=cart.shop,
                    created_at__gte=cart.updated_at,
                ).exists()

                if order_exists:
                    skipped_orders += 1
                    continue

                cart_url = reverse(
                    "cart",
                    kwargs={"shop_slug": cart.shop.slug},
                )

                one_hour_due = (
                    cart.reminder_1_sent_at is None
                    and cart.updated_at <= now - timedelta(hours=1)
                )

                if one_hour_due:
                    title = "Your cart is waiting"
                    message = (
                        f"You still have items in your "
                        f"{cart.shop.name} cart. Come back and "
                        "complete your order when you're ready."
                    )

                    notification = CustomerNotification.objects.create(
                        customer=cart.customer,
                        notification_type="cart_reminder",
                        title=title,
                        message=message,
                        target_url=cart_url,
                    )

                    cart.reminder_1_sent_at = now
                    cart.save(update_fields=["reminder_1_sent_at"])

                    transaction.on_commit(
                        lambda customer_id=cart.customer_id,
                        push_title=title,
                        push_body=message,
                        push_url=cart_url,
                        push_notification_id=notification.pk:
                            send_customer_push_notification(
                                customer_id=customer_id,
                                title=push_title,
                                body=push_body,
                                url=push_url,
                                notification_id=push_notification_id,
                            )
                    )

                    sent_first += 1
                    # Never send both reminders in the same execution.
                    continue

                second_due = (
                    cart.reminder_1_sent_at is not None
                    and cart.reminder_2_sent_at is None
                    and cart.updated_at <= now - timedelta(hours=24)
                    and cart.reminder_1_sent_at <= now - timedelta(hours=23)
                )

                if second_due:
                    title = "A reminder about your cart"
                    message = (
                        f"Your {cart.shop.name} cart still has "
                        "items waiting. Visit your cart if you'd "
                        "like to complete your order."
                    )

                    notification = CustomerNotification.objects.create(
                        customer=cart.customer,
                        notification_type="cart_reminder",
                        title=title,
                        message=message,
                        target_url=cart_url,
                    )

                    cart.reminder_2_sent_at = now
                    cart.save(update_fields=["reminder_2_sent_at"])

                    transaction.on_commit(
                        lambda customer_id=cart.customer_id,
                        push_title=title,
                        push_body=message,
                        push_url=cart_url,
                        push_notification_id=notification.pk:
                            send_customer_push_notification(
                                customer_id=customer_id,
                                title=push_title,
                                body=push_body,
                                url=push_url,
                                notification_id=push_notification_id,
                            )
                    )

                    sent_second += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Cart reminders completed. "
                f"First reminders: {sent_first}; "
                f"second reminders: {sent_second}; "
                f"carts skipped because an order exists: {skipped_orders}."
            )
        )