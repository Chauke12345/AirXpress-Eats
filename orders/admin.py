from django.contrib import admin

from .models import (
    Shop,
    StaffProfile,
    BraaiMaster,
    Driver,
    Category,
    MenuItem,
    Order,
    OrderItem,
    OrderStatusHistory,
)


# =========================================================
# SHOP / TENANT ADMIN
# =========================================================

@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "slug",
        "phone_number",
        "whatsapp_number",
        "location",
        "is_active",
        "created_at",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "name",
        "slug",
        "phone_number",
        "whatsapp_number",
        "location",
    )

    prepopulated_fields = {
        "slug": ("name",),
    }

    readonly_fields = (
        "created_at",
    )


# =========================================================
# STAFF PROFILE ADMIN
# =========================================================

@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "shop",
        "role",
        "is_active",
        "created_at",
    )

    list_filter = (
        "shop",
        "role",
        "is_active",
    )

    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
        "shop__name",
    )

    readonly_fields = (
        "created_at",
    )

    ordering = (
        "shop",
        "role",
        "user__username",
    )


# =========================================================
# BRAAI MASTER ADMIN
# =========================================================

@admin.register(BraaiMaster)
class BraaiMasterAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "shop",
        "is_available",
        "created_at",
    )

    list_filter = (
        "shop",
        "is_available",
    )

    search_fields = (
        "name",
        "shop__name",
    )

    readonly_fields = (
        "created_at",
    )


# =========================================================
# CATEGORY ADMIN
# =========================================================

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "shop",
        "display_order",
        "is_active",
    )

    list_filter = (
        "shop",
        "is_active",
    )

    search_fields = (
        "name",
        "shop__name",
    )

    ordering = (
        "shop",
        "display_order",
        "name",
    )


# =========================================================
# MENU ITEM ADMIN
# =========================================================

@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "shop",
        "category",
        "pricing_type",
        "price",
        "display_order",
        "is_available",
    )

    list_filter = (
        "shop",
        "category",
        "pricing_type",
        "is_available",
    )

    search_fields = (
        "name",
        "description",
        "shop__name",
    )

    ordering = (
        "shop",
        "category",
        "display_order",
        "name",
    )


# =========================================================
# ORDER ITEM INLINE
# =========================================================

class OrderItemInline(admin.TabularInline):

    model = OrderItem
    extra = 0

    fields = (
        "menu_item",
        "requested_amount",
        "quantity",
        "unit_price",
        "final_amount",
    )


# =========================================================
# ORDER STATUS HISTORY INLINE
# =========================================================

class OrderStatusHistoryInline(admin.TabularInline):

    model = OrderStatusHistory
    extra = 0

    readonly_fields = (
        "created_at",
    )


# =========================================================
# ORDER ADMIN
# =========================================================

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "customer_name",
        "shop",
        "braai_master",
        "order_type",
        "order_source",
        "status",
        "estimated_total",
        "final_total",
        "payment_status",
        "platform_fee",
        "platform_fee_paid",
        "created_at",
    )

    list_filter = (
        "shop",
        "order_type",
        "order_source",
        "status",
        "payment_status",
        "platform_fee_paid",
    )

    search_fields = (
        "customer_name",
        "whatsapp_number",
        "shop__name",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    inlines = (
        OrderItemInline,
        OrderStatusHistoryInline,
    )


# =========================================================
# ORDER ITEM ADMIN
# =========================================================

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):

    list_display = (
        "order",
        "menu_item",
        "requested_amount",
        "quantity",
        "unit_price",
        "final_amount",
    )

    list_filter = (
        "menu_item",
        "order__shop",
    )

    search_fields = (
        "order__customer_name",
        "menu_item__name",
        "order__shop__name",
    )


# =========================================================
# ORDER STATUS HISTORY ADMIN
# =========================================================

@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):

    list_display = (
        "order",
        "status",
        "created_at",
    )

    list_filter = (
        "status",
        "order__shop",
    )

    search_fields = (
        "order__customer_name",
        "order__shop__name",
    )

    ordering = (
        "-created_at",
    )
# =========================================================
# DRIVER ADMIN
# =========================================================

@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "shop",
        "is_available",
        "created_at",
    )

    list_filter = (
        "shop",
        "is_available",
    )

    search_fields = (
        "name",
        "shop__name",
    )

    readonly_fields = (
        "created_at",
    )


# =========================================================

