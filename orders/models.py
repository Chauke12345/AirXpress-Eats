from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models


# =========================================================
# SHOP / TENANT
# =========================================================

class Shop(models.Model):

    name = models.CharField(
        max_length=150
    )

    # Unique tenant identifier used in URLs.
    # Example:
    # /shop/example-shisanyama/
    slug = models.SlugField(
        max_length=160,
        unique=True,
        null=True,
        blank=True,
    )

    phone_number = models.CharField(
        max_length=20
    )

    whatsapp_number = models.CharField(
        max_length=20
    )

    address = models.TextField(
        blank=True
    )

    location = models.CharField(
        max_length=150,
        blank=True
    )

    
    # Exact map coordinates used for delivery routing.
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.name


# =========================================================
# STAFF PROFILE
# =========================================================

class StaffProfile(models.Model):

    ROLE_CHOICES = [
        (
            "owner",
            "Owner",
        ),
        (
            "manager",
            "Manager",
        ),
        (
            "staff",
            "Staff",
        ),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="staff_profile",
    )

    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="staff_profiles",
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="staff",
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return (
            f"{self.user.username} - "
            f"{self.shop.name} - "
            f"{self.get_role_display()}"
        )


# =========================================================
# BRAAI MASTER
# =========================================================

class BraaiMaster(models.Model):

    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="braai_masters"
    )

    name = models.CharField(
        max_length=100
    )

    is_available = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.name} - {self.shop.name}"


# =========================================================
# DRIVER
# =========================================================

class Driver(models.Model):

    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="drivers"
    )

    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="driver_profile",
    )

    name = models.CharField(
        max_length=100
    )

    is_available = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.name} - {self.shop.name}"


# =========================================================
# MENU CATEGORY
# =========================================================

class Category(models.Model):

    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="categories"
    )

    name = models.CharField(
        max_length=100
    )

    display_order = models.PositiveIntegerField(
        default=0
    )

    is_active = models.BooleanField(
        default=True
    )

    def __str__(self):
        return f"{self.name} - {self.shop.name}"

    class Meta:
        ordering = [
            "display_order",
            "name",
        ]

        verbose_name_plural = "Categories"


# =========================================================
# MENU ITEM
# =========================================================

class MenuItem(models.Model):

    PRICING_TYPES = [
        (
            "amount",
            "Customer Enters Amount",
        ),
        (
            "fixed",
            "Fixed Price",
        ),
    ]

    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="menu_items"
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="menu_items"
    )

    name = models.CharField(
        max_length=150
    )

    description = models.TextField(
        blank=True
    )

    pricing_type = models.CharField(
        max_length=20,
        choices=PRICING_TYPES,
        default="amount"
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    image = models.ImageField(
        upload_to="menu_items/",
        blank=True,
        null=True
    )

    display_order = models.PositiveIntegerField(
        default=0
    )

    is_available = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.name} - {self.shop.name}"

    class Meta:
        ordering = [
            "display_order",
            "name",
        ]


# =========================================================
# CUSTOMER ORDER
# =========================================================

class Order(models.Model):

    ORDER_TYPES = [
        (
            "delivery",
            "Delivery",
        ),
    ]

    # How the order entered the system.
    ORDER_SOURCE_CHOICES = [
        (
            "online",
            "Online",
        ),
    ]

    STATUS_CHOICES = [
        (
            "new",
            "Order Received",
        ),
        (
            "preparing",
            "Preparing Order",
        ),
        (
            "braaiing",
            "Braaiing",
        ),
        (
            "ready",
            "Ready for Delivery",
        ),
        (
            "driver_assigned",
            "Driver Assigned",
        ),
        (
            "picked_up",
            "Picked Up",
        ),
        (
            "delivered",
            "Delivered",
        ),
        (
            "collected",
            "Completed",
        ),
        (
            "cancelled",
            "Cancelled",
        ),
    ]

    PAYMENT_STATUS = [
        (
            "pending",
            "Payment Pending",
        ),
        (
            "paid",
            "Paid",
        ),
        (
            "failed",
            "Payment Failed",
        ),
        (
            "refunded",
            "Refunded",
        ),
    ]

    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="orders"
    )

    braai_master = models.ForeignKey(
        BraaiMaster,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders"
    )

    driver = models.ForeignKey(
        Driver,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders"
    )

    customer_name = models.CharField(
        max_length=150
    )

    whatsapp_number = models.CharField(
        max_length=20,
        blank=True
    )

    delivery_address = models.TextField(
        blank=True
    )
    # Where the customer is ordering from.
    order_type = models.CharField(
        max_length=20,
        choices=ORDER_TYPES
    )

    # How the order entered the system.
    order_source = models.CharField(
        max_length=20,
        choices=ORDER_SOURCE_CHOICES,
        default="online"
    )

    # Current progress of the order.
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="new"
    )

    # Total amount requested by the customer.
    estimated_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00")
    )

    # Delivery fee activated when the order is picked up.
    delivery_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00")
    )

    # Delivery distance recorded when the order is picked up.
    delivery_distance_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00")
    )

    # Final amount confirmed by the tenant/shop.
    final_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Internal AirXpress service charge.
    # Calculated as 15% of the food subtotal.
    # Not displayed separately to the customer.
    platform_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00")
    )

    # Internal driver payout.
    # Calculated as 40% of the delivery fee.
    # Not displayed to the customer.
    driver_payout = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00")
    )

    # Whether the tenant has settled the
    # AirXpress service charge with EdVance Tech.
    platform_fee_paid = models.BooleanField(
        default=False
    )

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS,
        default="pending"
    )

    # PayFast payment provider.
    payment_provider = models.CharField(
        max_length=30,
        default="payfast",
        blank=True
    )

    # Unique PayFast/order payment reference.
    payment_reference = models.CharField(
        max_length=100,
        blank=True
    )

    # Recorded only after PayFast confirms the payment.
    payment_paid_at = models.DateTimeField(
        null=True,
        blank=True
    )

    notes = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return (
            f"Order #{self.id} - "
            f"{self.customer_name} - "
            f"{self.shop.name}"
        )


# =========================================================
# ORDER ITEM
# =========================================================

class OrderItem(models.Model):

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items"
    )

    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.PROTECT
    )

    # Amount the customer wants to spend
    # on this specific product.
    requested_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    # Amount confirmed by the tenant/shop
    # after the product has been prepared/weighed.
    final_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Used for fixed-price items.
    quantity = models.PositiveIntegerField(
        default=1
    )

    # Price per fixed-price item at the time
    # the customer placed the order.
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    def __str__(self):
        return (
            f"{self.menu_item.name} - "
            f"R{self.requested_amount} - "
            f"Order #{self.order.id}"
        )


# =========================================================
# ORDER STATUS HISTORY
# =========================================================

class OrderStatusHistory(models.Model):

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="status_history"
    )

    status = models.CharField(
        max_length=20,
        choices=Order.STATUS_CHOICES
    )

    notes = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = [
            "created_at",
        ]

        verbose_name_plural = (
            "Order status histories"
        )

    def __str__(self):
        return (
            f"Order #{self.order.id} - "
            f"{self.get_status_display()}"
        )

class DeliveryPricing(models.Model):

    shop = models.OneToOneField(
        Shop,
        on_delete=models.CASCADE,
        related_name="delivery_pricing",
    )

    max_radius_km = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("12.00"),
    )

    driver_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("40.00"),
    )

    service_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("15.00"),
    )

    business_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("45.00"),
    )

    def __str__(self):
        return f"{self.shop.name} - Delivery Pricing"

class DeliveryRate(models.Model):

    delivery_pricing = models.ForeignKey(
        DeliveryPricing,
        on_delete=models.CASCADE,
        related_name="rates",
    )

    max_distance_km = models.DecimalField(
        max_digits=5,
        decimal_places=2,
    )

    delivery_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    class Meta:
        ordering = ["max_distance_km"]

    def __str__(self):
        return (
            f"{self.delivery_pricing.shop.name} - "
            f"{self.max_distance_km} km - "
            f"R{self.delivery_fee}"
        )

class ShopSubscriptionPayment(models.Model):
    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="subscription_payments",
    )

    year = models.PositiveIntegerField()
    month = models.PositiveSmallIntegerField()

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("500.00"),
    )

    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["shop", "year", "month"],
                name="unique_shop_monthly_subscription",
            )
        ]
        ordering = ["-year", "-month", "shop__name"]

    def __str__(self):
        return (
            f"{self.shop.name} - "
            f"{self.year}-{self.month:02d} - "
            f"R{self.amount}"
        )















# =========================================================
# DRIVER PAYOUT
# =========================================================

class DriverPayout(models.Model):

    STATUS_CHOICES = [
        (
            "pending",
            "Pending",
        ),
        (
            "paid",
            "Paid",
        ),
    ]

    driver = models.ForeignKey(
        Driver,
        on_delete=models.CASCADE,
        related_name="payouts",
    )

    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="driver_payout_record",
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return (
            f"Driver Payout - "
            f"Order #{self.order.id} - "
            f"{self.driver.name} - "
            f"R{self.amount}"
        )


# =========================================================
# DELIVERY REQUEST
# =========================================================

class DeliveryRequest(models.Model):

    STATUS_CHOICES = [
        (
            "pending",
            "Pending",
        ),
        (
            "accepted",
            "Accepted",
        ),
        (
            "declined",
            "Declined",
        ),
        (
            "expired",
            "Expired",
        ),
    ]

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="delivery_requests",
    )

    driver = models.ForeignKey(
        Driver,
        on_delete=models.CASCADE,
        related_name="delivery_requests",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    responded_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    def __str__(self):
        return (
            f"Delivery Request - "
            f"Order #{self.order.id} - "
            f"{self.driver.name} - "
            f"{self.status}"
        )

