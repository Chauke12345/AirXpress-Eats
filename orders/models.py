from decimal import Decimal
import uuid

from django.contrib.auth.models import User
from django.db import models


# =========================================================
# SHOP / TENANT
# =========================================================

class Shop(models.Model):

    name = models.CharField(
        max_length=150
    )

    logo = models.ImageField(
        upload_to="shop_logos/",
        blank=True,
        null=True,
    )

    # Unique tenant identifier used in URLs.
    # Example:
    # Example shop URL pattern
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
    # Shop banking details for verified weekly payouts.
    bank_name = models.CharField(max_length=100, blank=True)
    account_holder_name = models.CharField(max_length=150, blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    account_type = models.CharField(max_length=30, blank=True)
    branch_code = models.CharField(max_length=20, blank=True)

    banking_status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending Verification"),
            ("verified", "Verified"),
            ("rejected", "Rejected"),
        ],
        default="pending",
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


# =========================================================`r`n# DRIVER`r`n# =========================================================
# =========================================================
# DRIVER
# =========================================================

class Driver(models.Model):

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
    photo = models.ImageField(
        upload_to="drivers/",
        blank=True,
        null=True,
    )

    driver_license = models.FileField(
        upload_to="driver_licenses/",
        blank=True,
        null=True,
    )

    license_verification_status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending Verification"),
            ("verified", "Verified"),
            ("rejected", "Rejected"),
        ],
        default="pending",
    )

    airxpress_verified = models.BooleanField(
        default=False,
    )
    vehicle_make_model = models.CharField(
        max_length=100,
        blank=True,
    )

    vehicle_colour = models.CharField(
        max_length=50,
        blank=True,
    )

    vehicle_registration = models.CharField(
        max_length=20,
        blank=True,
    )

    bank_name = models.CharField(
        max_length=100,
        blank=True,
    )

    account_holder_name = models.CharField(
        max_length=150,
        blank=True,
    )

    account_number = models.CharField(
        max_length=50,
        blank=True,
    )

    account_type = models.CharField(
        max_length=50,
        blank=True,
    )

    physical_address = models.TextField(
        blank=True,
        default="",
        help_text="Driver physical address obtained from banking information.",
    )
    branch_code = models.CharField(
        max_length=20,
        blank=True,
    )

    banking_status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending Verification"),
            ("verified", "Verified"),
        ],
        default="pending",
    )


    is_available = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.name


# =========================================================
# CUSTOMER PROFILE
# =========================================================

class CustomerProfile(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="customer_profile",
    )

    must_change_password = models.BooleanField(
        default=False,
        help_text="Require the customer to change their temporary password at next login.",
    )
    whatsapp_number = models.CharField(
        max_length=20,
        blank=True,
    )

    bank_name = models.CharField(
        max_length=100,
        blank=True,
    )

    account_holder_name = models.CharField(
        max_length=150,
        blank=True,
    )

    account_number = models.CharField(
        max_length=50,
        blank=True,
    )

    account_type = models.CharField(
        max_length=30,
        blank=True,
    )

    physical_address = models.TextField(
        blank=True,
        default="",
        help_text="Driver physical address obtained from banking information.",
    )
    branch_code = models.CharField(
        max_length=20,
        blank=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return self.user.username

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

    HOMEPAGE_CATEGORY_CHOICES = [
        ("popular", "Popular Picks"),
        ("main_meals", "Main Meals"),
        ("burgers", "Burgers"),
        ("chicken", "Chicken"),
        ("meat_braai", "Meat & Braai"),
        ("sides", "Sides"),
        ("drinks", "Drinks"),
        ("desserts", "Desserts"),
        ("groceries", "Groceries"),
    ]

    is_homepage_featured = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Show this item in the Popular Picks section on the public homepage.",
    )

    homepage_category = models.CharField(
        max_length=30,
        choices=HOMEPAGE_CATEGORY_CHOICES,
        blank=True,
        default="",
        db_index=True,
        help_text="Optional shared category used to group this item on the public homepage.",
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
    driver = models.ForeignKey(
        Driver,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders"
    )

    
    driver_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    driver_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    driver_location_updated_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    customer_account = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="airxpress_orders",
    )

    customer_name = models.CharField(
        max_length=150
    )

    
    # Secure delivery QR token; valid until used or the order is cancelled.
    delivery_qr_token = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        db_index=True,
    )
    tracking_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )
    whatsapp_number = models.CharField(
        max_length=20,
        blank=True
    )

    # Timestamp for single-use customer QR verification.
    delivery_qr_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
    )
    # Customer delivery OTP verification.
    delivery_otp_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )

    delivery_otp_expires_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    delivery_otp_attempts = models.PositiveSmallIntegerField(
        default=0,
    )

    delivery_otp_verified_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    delivery_address = models.TextField(
        blank=True
    )
    
    customer_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    customer_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
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
    # AirXpress service charge.
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

    # Original food amount belonging to the shop,
    # excluding the AirXpress markup.
    shop_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
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

    # Snapshot of extras selected when the customer ordered.
    extras = models.JSONField(
        default=list,
        blank=True,
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

    payment_reference = models.CharField(
        max_length=100,
        blank=True,
    )

    payment_notes = models.TextField(
        blank=True,
    )

    statement_number = models.CharField(
        max_length=50,
        blank=True,
        unique=True,
        null=True,
    )

    batch = models.ForeignKey(
        "DriverPayoutBatch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payouts",
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
# WEEKLY DRIVER PAYOUT BATCH
# =========================================================

class DriverPayoutBatch(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("paid", "Paid"),
    ]

    driver = models.ForeignKey(
        Driver,
        on_delete=models.PROTECT,
        related_name="payout_batches",
    )

    week_start = models.DateField()
    week_end = models.DateField()

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    payment_reference = models.CharField(
        max_length=100,
        blank=True,
    )

    payment_notes = models.TextField(
        blank=True,
    )

    statement_number = models.CharField(
        max_length=50,
        unique=True,
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-week_start", "driver__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["driver", "week_start", "week_end"],
                name="unique_driver_weekly_payout_batch",
            ),
        ]

    def __str__(self):
        return (
            f"Weekly payout - {self.driver.name} - "
            f"{self.week_start} to {self.week_end}"
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







# =========================================================
# DRIVER WEB PUSH SUBSCRIPTIONS
# =========================================================

class DriverPushSubscription(models.Model):
    driver = models.ForeignKey(
        Driver,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint = models.TextField(unique=True)
    p256dh = models.TextField()
    auth = models.TextField()
    user_agent = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Push subscription - {self.driver.name}"


# =========================================================
# CUSTOMER REVIEW
# =========================================================

class OrderReview(models.Model):

    RATING_CHOICES = [
        (1, "1 Star"),
        (2, "2 Stars"),
        (3, "3 Stars"),
        (4, "4 Stars"),
        (5, "5 Stars"),
    ]

    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="review",
    )

    customer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="order_reviews",
    )

    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        related_name="reviews",
    )

    driver = models.ForeignKey(
        Driver,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviews",
    )

    overall_rating = models.PositiveSmallIntegerField(
        choices=RATING_CHOICES,
    )

    food_rating = models.PositiveSmallIntegerField(
        choices=RATING_CHOICES,
    )

    delivery_rating = models.PositiveSmallIntegerField(
        choices=RATING_CHOICES,
    )

    comment = models.TextField(
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
            f"Review - Order #{self.order.id} - "
            f"{self.overall_rating}/5"
        )



# =========================================================
# SHOP PAYOUTS AND WEEKLY BATCHES
# =========================================================

class ShopPayoutBatch(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("paid", "Paid"),
    ]

    shop = models.ForeignKey(
        Shop,
        on_delete=models.PROTECT,
        related_name="payout_batches",
    )
    week_start = models.DateField()
    week_end = models.DateField()
    total_food_sales = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    total_commission = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending"
    )
    payment_reference = models.CharField(max_length=100, blank=True)
    payment_notes = models.TextField(blank=True)
    statement_number = models.CharField(max_length=50, unique=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-week_start", "shop__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["shop", "week_start", "week_end"],
                name="unique_shop_weekly_payout_batch",
            ),
        ]

    def __str__(self):
        return f"{self.shop.name} - {self.week_start} to {self.week_end}"


class ShopPayout(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("paid", "Paid"),
    ]

    shop = models.ForeignKey(
        Shop,
        on_delete=models.PROTECT,
        related_name="payouts",
    )
    order = models.OneToOneField(
        Order,
        on_delete=models.PROTECT,
        related_name="shop_payout_record",
    )
    food_sales = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    commission = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending"
    )
    payment_reference = models.CharField(max_length=100, blank=True)
    payment_notes = models.TextField(blank=True)
    statement_number = models.CharField(
        max_length=50, unique=True, null=True, blank=True
    )
    batch = models.ForeignKey(
        ShopPayoutBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payouts",
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.shop.name} - Order #{self.order_id} - R{self.amount}"
from django.utils import timezone


class SupportTicket(models.Model):
    CATEGORY_CHOICES = [
        ("technical", "Technical Support"),
        ("operations", "Operations Support"),
        ("general", "General Enquiry"),
    ]

    PRIORITY_CHOICES = [
        ("normal", "Normal"),
        ("high", "High"),
        ("critical", "Critical"),
    ]

    STATUS_CHOICES = [
        ("open", "Open"),
        ("in_progress", "In Progress"),
        ("resolved", "Resolved"),
    ]

    reference = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )
    customer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="airxpress_support_tickets",
    )
    customer_name = models.CharField(max_length=150, blank=True)
    customer_phone = models.CharField(max_length=30, blank=True)
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default="general",
    )
    subject = models.CharField(max_length=200)
    description = models.TextField()
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default="normal",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="open",
    )
    assigned_team = models.CharField(max_length=30, default="operations")
    requires_escalation = models.BooleanField(default=False)
    escalation_notes = models.TextField(blank=True)
    staff_notes = models.TextField(blank=True)
    customer_response = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.status == "resolved" and self.resolved_at is None:
            self.resolved_at = timezone.now()
        elif self.status != "resolved":
            self.resolved_at = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Support #{str(self.reference)[:8]} - {self.subject}"

# =========================================================
# CUSTOMER REFUND REQUEST
# =========================================================

class RefundRequest(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending Review"),
        ("under_review", "Under Review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("paid", "Refund Paid"),
    ]

    reference = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="refund_requests",
    )

    customer = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="airxpress_refund_requests",
    )

    reason = models.TextField()

    requested_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )

    staff_notes = models.TextField(blank=True)

    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_airxpress_refunds",
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    notification_sent_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    notification_sent_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_airxpress_refund_notifications",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Refund {str(self.reference)[:8]} - Order #{self.order_id}"



# =========================================================
# REFUND AUDIT LOG
# =========================================================

class RefundAuditLog(models.Model):
    EVENT_CHOICES = [
        ("status_changed", "Status Changed"),
        ("notification_recorded", "Notification Recorded"),
        ("note_updated", "Internal Notes Updated"),
    ]

    refund = models.ForeignKey(
        RefundRequest,
        on_delete=models.PROTECT,
        related_name="audit_logs",
    )

    event_type = models.CharField(
        max_length=40,
        choices=EVENT_CHOICES,
        default="status_changed",
        db_index=True,
    )

    previous_status = models.CharField(
        max_length=30,
        blank=True,
    )

    new_status = models.CharField(
        max_length=30,
        blank=True,
    )

    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="airxpress_refund_audit_events",
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return (
            f"Refund audit {self.refund_id}: "
            f"{self.event_type} at {self.created_at}"
        )
