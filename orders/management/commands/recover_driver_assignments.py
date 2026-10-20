from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from orders.models import (
    DeliveryRequest,
    Driver,
    Order,
    OrderStatusHistory,
)
from orders.views import dispatch_order_to_available_drivers


class Command(BaseCommand):
    help = (
        "Expire stale driver offers and recover accepted assignments "
        "that have not progressed to pickup."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report eligible records without changing anything.",
        )
        parser.add_argument(
            "--offer-minutes",
            type=int,
            default=3,
            help="Minutes before a pending driver offer expires.",
        )
        parser.add_argument(
            "--pickup-minutes",
            type=int,
            default=10,
            help="Minutes after acceptance before recovery.",
        )
        parser.add_argument(
            "--exclude-order-ids",
            default="",
            help="Comma-separated order IDs to exclude from recovery and redispatch.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        offer_minutes = options["offer_minutes"]
        pickup_minutes = options["pickup_minutes"]
        dry_run = options["dry_run"]
        try:
            excluded_order_ids = {
                int(value.strip())
                for value in options["exclude_order_ids"].split(",")
                if value.strip()
            }
        except ValueError:
            self.stderr.write(self.style.ERROR(
                "--exclude-order-ids must contain comma-separated integers."
            ))
            return
        if any(order_id < 1 for order_id in excluded_order_ids):
            self.stderr.write(self.style.ERROR(
                "Excluded order IDs must be positive integers."
            ))
            return

        if offer_minutes < 1 or pickup_minutes < 1:
            self.stderr.write(
                self.style.ERROR("Timeouts must be at least 1 minute.")
            )
            return

        offer_cutoff = now - timedelta(minutes=offer_minutes)
        pickup_cutoff = now - timedelta(minutes=pickup_minutes)

        eligible_order_filter = Q(
            order__status="ready",
            order__payment_status="paid",
            order__order_type="delivery",
            order__driver__isnull=True,
        )

        stale_pending = DeliveryRequest.objects.filter(
            status="pending",
            created_at__lte=offer_cutoff,
        ).filter(eligible_order_filter)
        if excluded_order_ids:
            stale_pending = stale_pending.exclude(
                order_id__in=excluded_order_ids
            )

        stale_accepted = DeliveryRequest.objects.filter(
            status="accepted",
            responded_at__isnull=False,
            responded_at__lte=pickup_cutoff,
            order__status="driver_assigned",
            order__driver_id__isnull=False,
            order__payment_status="paid",
            order__order_type="delivery",
        )
        if excluded_order_ids:
            stale_accepted = stale_accepted.exclude(
                order_id__in=excluded_order_ids
            )

        # Retry eligible orders that have no active pending offer.
        # This also handles orders for which the previous dispatch
        # found no available drivers.
        retry_candidates = Order.objects.filter(
            status="ready",
            payment_status="paid",
            order_type="delivery",
            driver__isnull=True,
        ).exclude(
            delivery_requests__status__in=["pending", "accepted"]
        )
        if excluded_order_ids:
            retry_candidates = retry_candidates.exclude(
                id__in=excluded_order_ids
            )

        if dry_run:
            self.stdout.write(
                f"Stale eligible pending offers: {stale_pending.count()}"
            )
            self.stdout.write(
                "Accepted assignments eligible for recovery: "
                f"{stale_accepted.count()}"
            )
            self.stdout.write(
                "Ready orders eligible for redispatch: "
                f"{retry_candidates.distinct().count()}"
            )
            self.stdout.write(
                "DRY RUN: no records were changed and no notifications were sent."
            )
            return

        # Expire only pending offers whose orders are still ready,
        # paid, delivery orders without an assigned driver.
        stale_pending_ids = list(
            stale_pending.values_list("id", flat=True)
        )
        expired_pending_count = 0
        retry_order_ids = set()

        for request_id in stale_pending_ids:
            with transaction.atomic():
                request_obj = (
                    DeliveryRequest.objects.select_for_update()
                    .filter(id=request_id, status="pending")
                    .first()
                )
                if request_obj is None:
                    continue

                order = (
                    Order.objects.select_for_update()
                    .filter(id=request_obj.order_id)
                    .first()
                )
                if (
                    order is None
                    or order.status != "ready"
                    or order.payment_status != "paid"
                    or order.order_type != "delivery"
                    or order.driver_id is not None
                    or request_obj.created_at > offer_cutoff
                ):
                    continue

                request_obj.status = "expired"
                request_obj.responded_at = now
                request_obj.save(
                    update_fields=["status", "responded_at"]
                )
                expired_pending_count += 1
                retry_order_ids.add(order.id)

        recovered_count = 0

        # Recover only an assignment still owned by the accepting driver.
        for request_id in stale_accepted.values_list("id", flat=True).iterator():
            with transaction.atomic():
                request_obj = (
                    DeliveryRequest.objects.select_for_update()
                    .select_related("driver")
                    .filter(id=request_id, status="accepted")
                    .first()
                )
                if (
                    request_obj is None
                    or request_obj.responded_at is None
                    or request_obj.responded_at > pickup_cutoff
                ):
                    continue

                order = (
                    Order.objects.select_for_update()
                    .filter(id=request_obj.order_id)
                    .first()
                )
                if (
                    order is None
                    or order.status != "driver_assigned"
                    or order.driver_id != request_obj.driver_id
                    or order.payment_status != "paid"
                    or order.order_type != "delivery"
                ):
                    continue

                driver = request_obj.driver

                request_obj.status = "expired"
                request_obj.save(update_fields=["status"])

                order.driver = None
                order.status = "ready"
                order.save(
                    update_fields=["driver", "status", "updated_at"]
                )

                has_other_active_order = Order.objects.filter(
                    driver=driver,
                    status__in=[
                        "driver_assigned",
                        "picked_up",
                        "on_the_way",
                    ],
                ).exclude(id=order.id).exists()

                if not has_other_active_order:
                    Driver.objects.filter(id=driver.id).update(
                        is_available=True
                    )

                OrderStatusHistory.objects.create(
                    order=order,
                    status="ready",
                    notes=(
                        f"Driver {driver.name} did not collect the order "
                        f"within {pickup_minutes} minutes of acceptance. "
                        "Assignment released for redispatch."
                    ),
                )

                retry_order_ids.add(order.id)
                recovered_count += 1

        # Re-evaluate candidates after expiring offers and recovering
        # assignments. Do not create duplicate offers when pending
        # requests still exist.
        retry_order_ids.update(
            Order.objects.filter(
                status="ready",
                payment_status="paid",
                order_type="delivery",
                driver__isnull=True,
            ).exclude(
                delivery_requests__status__in=["pending", "accepted"]
            ).values_list("id", flat=True)
        )

        if excluded_order_ids:
            retry_order_ids.difference_update(excluded_order_ids)

        dispatched_count = 0

        for order in Order.objects.filter(
            id__in=retry_order_ids,
            status="ready",
            payment_status="paid",
            order_type="delivery",
            driver__isnull=True,
        ).distinct():
            if DeliveryRequest.objects.filter(
                order=order,
                status__in=["pending", "accepted"],
            ).exists():
                continue
            try:
                dispatched_count += dispatch_order_to_available_drivers(order)
            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(
                        f"Dispatch failed for order #{order.id}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                )
