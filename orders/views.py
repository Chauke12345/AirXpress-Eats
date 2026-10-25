import json
import math
import secrets
import hashlib
import hmac
import uuid
import base64
import qrcode
from datetime import timedelta
from pathlib import Path
from decimal import Decimal, InvalidOperation
from django.contrib.auth.password_validation import validate_password

from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib import messages

from django.contrib.auth import (
    authenticate,
    login,
    logout,
    update_session_auth_hash,
)

from django.contrib.auth.decorators import (
    login_required,
    user_passes_test,

)

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from django.http import JsonResponse
from django.http import HttpResponse
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib import colors
from django.shortcuts import (
    render,
    redirect,
    get_object_or_404,
)

from django.utils import timezone
from django.db import models
from django.db import transaction
from django.db.models import Sum, Count, Avg
from django.urls import reverse

from .forms import (
    CustomerOrderForm,
)

from .models import (
    Category,
    CustomerProfile,
    Driver,
    DriverPushSubscription,
    DriverPayout,
    DriverPayoutBatch,
    ShopPayout,
    ShopPayoutBatch,
    DeliveryRequest,
    DeliveryRate,
    MenuItem,
    Order,
    OrderItem,
    OrderStatusHistory,
    OrderReview,
    RefundRequest,
    RefundAuditLog,
    Shop,
    StaffProfile,
    ShopSubscriptionPayment,
    SupportTicket
)

from .mapbox import MapboxError, calculate_driving_distance, calculate_driving_distance_to_coordinates, calculate_driver_route
from .services import send_delivery_otp_sms
def _delivery_otp_hash(order_id, code):
    """Hash a delivery OTP for one specific order."""
    value = f"{order_id}:{code}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _generate_delivery_otp(order):
    """Generate and store a short-lived customer delivery OTP."""
    code = f"{secrets.randbelow(1_000_000):06d}"

    order.delivery_otp_hash = _delivery_otp_hash(order.id, code)
    order.delivery_otp_expires_at = timezone.now() + timedelta(minutes=10)
    order.delivery_otp_attempts = 0
    order.delivery_otp_verified_at = None

    order.save(update_fields=[
        "delivery_otp_hash",
        "delivery_otp_expires_at",
        "delivery_otp_attempts",
        "delivery_otp_verified_at",
        "updated_at",
    ])

    return code


def _verify_delivery_otp(order, submitted_code):
    """Verify a delivery OTP without exposing the stored code."""
    if order.delivery_otp_verified_at:
        return False, "This delivery has already been verified."

    if not order.delivery_otp_hash or not order.delivery_otp_expires_at:
        return False, "No active delivery code exists."

    if order.delivery_otp_attempts >= 5:
        return False, "Too many incorrect attempts. A new code is required."

    if timezone.now() >= order.delivery_otp_expires_at:
        return False, "The delivery code has expired. A new code is required."

    order.delivery_otp_attempts += 1

    expected_hash = order.delivery_otp_hash
    submitted_hash = _delivery_otp_hash(order.id, submitted_code)

    if not hmac.compare_digest(expected_hash, submitted_hash):
        order.save(update_fields=["delivery_otp_attempts", "updated_at"])
        return False, "Incorrect delivery code."

    order.delivery_otp_verified_at = timezone.now()
    order.save(update_fields=[
        "delivery_otp_attempts",
        "delivery_otp_verified_at",
        "updated_at",
    ])

    return True, "Customer delivery code verified."


# =========================================================
# CUSTOMER ORDER PAGE
# =========================================================


# =========================================================
# PUBLIC AIRXPRESS EATS HOMEPAGE
# =========================================================

# =========================================================
# MAPBOX ADDRESS AUTOCOMPLETE
# =========================================================

def address_suggestions(request):
    """
    Return Mapbox address suggestions for the checkout address field.
    The Mapbox token stays server-side.
    """
    query = request.GET.get("q", "").strip()

    if len(query) < 3:
        return JsonResponse(
            {"suggestions": []}
        )

    token = getattr(
        settings,
        "MAPBOX_TOKEN",
        "",
    )

    if not token:
        return JsonResponse(
            {"suggestions": []},
            status=503,
        )

    import urllib.parse
    import urllib.request
    import json

    params = urllib.parse.urlencode(
        {
            "q": query,
            "country": "ZA",
            "language": "en",
            "limit": 5,
            "access_token": token,
        }
    )

    url = (
        "https://api.mapbox.com/search/geocode/v6/forward?"
        + params
    )

    try:
        with urllib.request.urlopen(
            url,
            timeout=5,
        ) as response:
            data = json.loads(
                response.read().decode("utf-8")
            )

        suggestions = []

        for feature in data.get("features", []):
            properties = feature.get(
                "properties",
                {},
            )

            suggestions.append(
                {
                    "id": feature.get("id", ""),
                    "name": properties.get(
                        "name",
                        "",
                    ),
                    "full_address": properties.get(
                        "full_address",
                        properties.get(
                            "name",
                            "",
                        ),
                    ),
                }
            )

        return JsonResponse(
            {
                "suggestions": suggestions,
            }
        )

    except Exception:
        return JsonResponse(
            {"suggestions": []},
            status=502,
        )


def gps_reverse_geocode(request):
    """Resolve a customer's confirmed map-pin coordinates to an address."""
    from django.views.decorators.http import require_GET

    if request.method != "GET":
        return JsonResponse(
            {"error": "GET requests only."},
            status=405,
        )

    try:
        latitude = float(request.GET.get("lat", ""))
        longitude = float(request.GET.get("lon", ""))
    except (TypeError, ValueError):
        return JsonResponse(
            {"error": "Valid latitude and longitude are required."},
            status=400,
        )

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return JsonResponse(
            {"error": "Coordinates are outside valid ranges."},
            status=400,
        )

    token = getattr(settings, "MAPBOX_TOKEN", "")
    if not token:
        return JsonResponse(
            {"error": "Location service is not configured."},
            status=503,
        )

    import urllib.parse
    import urllib.request
    import json

    params = urllib.parse.urlencode({
        "longitude": longitude,
        "latitude": latitude,
        "country": "ZA",
        "language": "en",
        "limit": 1,
        "access_token": token,
    })
    url = (
        "https://api.mapbox.com/search/geocode/v6/reverse?"
        + params
    )

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))

        features = data.get("features", [])
        if not features:
            return JsonResponse(
                {"error": "No address found for this pin. Please adjust it or enter your address manually."},
                status=404,
            )

        properties = features[0].get("properties", {})
        address = (
            properties.get("full_address")
            or properties.get("name")
            or ""
        ).strip()

        if not address:
            return JsonResponse(
                {"error": "No readable address found for this pin."},
                status=404,
            )

        return JsonResponse({
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
        })

    except Exception:
        return JsonResponse(
            {"error": "Could not look up this location. Please try again or enter the address manually."},
            status=502,
        )

def home(request):
    """
    Public AirXpress Eats marketplace homepage.
    """
    shops = Shop.objects.filter(
        is_active=True
    ).order_by("name")

    # AIRXPRESS RESTAURANT AREA GROUPING 2026
    sorted_shops = sorted(
        shops,
        key=lambda shop: (
            (shop.location or "").strip().casefold() or "other locations",
            shop.name.casefold(),
        ),
    )
    restaurant_groups = []
    for shop in sorted_shops:
        location = (shop.location or "").strip()
        group_key = location.casefold() or "other locations"
        if not restaurant_groups or restaurant_groups[-1]["key"] != group_key:
            restaurant_groups.append({
                "key": group_key,
                "location": location or "Other locations",
                "shops": [],
            })
        restaurant_groups[-1]["shops"].append(shop)

    available_items = MenuItem.objects.filter(
        shop__is_active=True,
        is_available=True,
        price__gte=Decimal("45.00"),
    ).select_related(
        "shop",
        "category",
    )

    homepage_categories = [
        ("main_meals", "Main Meals"),
        ("burgers", "Burgers"),
        ("chicken", "Chicken"),
        ("meat_braai", "Meat & Braai"),
        ("sides", "Sides"),
        ("drinks", "Drinks"),
        ("desserts", "Desserts"),
        ("groceries", "Groceries"),
    ]

    category_rows = []
    for key, label in homepage_categories:
        items = available_items.filter(
            homepage_category=key
        ).order_by("name")

        if items.exists():
            category_rows.append({
                "key": key,
                "label": label,
                "items": items,
            })

    # Fair-share Popular Picks: rotate shops weekly, then select
    # one eligible product per shop before filling remaining slots.
    from datetime import date

    eligible_items = list(
        available_items.filter(
            homepage_category__gt="",
        ).order_by("shop_id", "pk")
    )

    shop_items = {}
    for item in eligible_items:
        shop_items.setdefault(item.shop_id, []).append(item)

    shop_ids = sorted(shop_items)
    popular_items = []

    if shop_ids:
        rotation_anchor = date(2024, 1, 1)
        week_index = (date.today() - rotation_anchor).days // 7
        shop_start = week_index % len(shop_ids)
        rotated_shop_ids = shop_ids[shop_start:] + shop_ids[:shop_start]

        # Give each of five shops one slot where possible.
        selected_shop_ids = rotated_shop_ids[:5]
        for shop_id in selected_shop_ids:
            products = shop_items[shop_id]
            product_index = week_index % len(products)
            popular_items.append(products[product_index])

        # If fewer than five shops qualify, fill remaining slots
        # with other products without duplicating a product.
        if len(popular_items) < 5:
            selected_ids = {item.pk for item in popular_items}
            remaining = [
                item for shop_id in rotated_shop_ids
                for item in shop_items[shop_id]
                if item.pk not in selected_ids
            ]
            offset = week_index % len(remaining) if remaining else 0
            remaining = remaining[offset:] + remaining[:offset]
            popular_items.extend(remaining[:5 - len(popular_items)])

    # Apply the same customer-facing markup used by the menu.
    # Keep MenuItem.price unchanged for shop accounting and payouts.
    for row in category_rows:
        for item in row["items"]:
            item.customer_price = (
                (item.price or Decimal("0.00")) * Decimal("1.25")
            ).quantize(Decimal("0.01"))

    # Mozeka & Sons: assign weekday menu headings.
    if shop.pk == 20 and shop.name == "Mozeka & Sons Catering Services":
        for item in menu_items:
            if item.name.startswith("Thursday - "):
                item.menu_day = "Thursday Menu"
            elif item.name.startswith("Friday - "):
                item.menu_day = "Friday Menu"
            elif item.name.startswith("Saturday - "):
                item.menu_day = "Saturday Menu"
            elif item.name.startswith("Sunday Lunch - "):
                item.menu_day = "Sunday Lunch Menu"
            elif item.name.startswith("Monday - African Cuisine - "):
                item.menu_day = "Monday â€” African Cuisine"
            else:
                item.menu_day = "Other Menu"

    # Assign separately to the actual objects used by Popular Picks.
    for item in popular_items:
        item.customer_price = (
            (item.price or Decimal("0.00")) * Decimal("1.25")
        ).quantize(Decimal("0.01"))

    context = {
        "shops": shops,
        "restaurant_groups": restaurant_groups,
        "total_shops": shops.count(),
        "categories": Category.objects.filter(
            menu_items__shop__is_active=True
        ).distinct().order_by("name"),
        "featured_items": popular_items,
        "homepage_categories": homepage_categories,
        "category_rows": category_rows,
        "popular_items": popular_items,
    }

    return render(
        request,
        "orders/home.html",
        context,
    )


def refund_policy(request):
    """Display the public AirXpress Eats refund policy."""
    return render(request, "orders/refund_policy.html")



# Optional extras for Naledi's Slay & Takeaway.
# Prices here are shop base prices; customer markup is calculated separately.
NALEDI_EXTRAS_CATALOG = (
    ("extra_slice", "Extra slice", Decimal("3.00")),
    ("egg", "Egg", Decimal("4.00")),
    ("cheese", "Cheese", Decimal("4.00")),
    ("special", "Special", Decimal("4.00")),
    ("polony", "Polony", Decimal("4.00")),
    ("vienna", "Vienna", Decimal("7.00")),
    ("avocado", "Avocado", Decimal("8.00")),
    ("gherkins", "Gherkins", Decimal("8.00")),
    ("fried_onions", "Fried onions", Decimal("8.00")),
    ("ham", "Ham", Decimal("15.00")),
    ("beef_patty", "Beef patty", Decimal("20.00")),
    ("chicken_crumbled", "Chicken crumbled", Decimal("20.00")),
    ("burger_patty", "Burger patty", Decimal("20.00")),
    ("smoked_russian", "Smoked Russian", Decimal("20.00")),
)

def add_to_cart(request, shop_slug, menu_item_id):

    shop = get_object_or_404(
        Shop,
        slug=shop_slug,
        is_active=True,
    )
    menu_item = get_object_or_404(
        MenuItem,
        id=menu_item_id,
        shop=shop,
        is_available=True,
    )
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if menu_item.price is None or menu_item.price < Decimal("45.00"):
        message = "This item is unavailable because its base price is below R45."
        if is_ajax:
            return JsonResponse({"success": False, "message": message}, status=400)
        messages.error(request, message)
        return redirect("customer_order", shop_slug=shop_slug)
    cart = request.session.get("cart", {})

    if menu_item.pricing_type == "fixed":
        try:
            quantity = int(request.POST.get("quantity", "1"))
        except (TypeError, ValueError):
            quantity = 1
        quantity = max(1, quantity)

        selected_extras = []
        if shop.pk == 8:
            selected_ids = set(request.POST.getlist("extras"))
            catalog = {
                extra_id: (name, base_price)
                for extra_id, name, base_price in NALEDI_EXTRAS_CATALOG
            }
            if not selected_ids.issubset(catalog.keys()):
                error_message = "One or more selected extras are invalid."
                if is_ajax:
                    return JsonResponse(
                        {"success": False, "message": error_message},
                        status=400,
                    )
                messages.error(request, error_message)
                return redirect("customer_order", shop_slug=shop.slug)

            for extra_id in sorted(selected_ids):
                name, base_price = catalog[extra_id]
                customer_price = (
                    base_price * Decimal("1.25")
                ).quantize(Decimal("0.01"))
                selected_extras.append({
                    "id": extra_id,
                    "name": name,
                    "base_price": str(base_price),
                    "customer_price": str(customer_price),
                })

        extra_key = ",".join(extra["id"] for extra in selected_extras)
        item_key = (
            f"{menu_item.id}__{extra_key}"
            if extra_key else str(menu_item.id)
        )

        if item_key in cart:
            cart[item_key]["quantity"] = (
                int(cart[item_key].get("quantity", 1)) + quantity
            )
        else:
            cart[item_key] = {
                "quantity": quantity,
                "extras": selected_extras,
            }

    else:
        amount = request.POST.get("amount", "").strip()
        try:
            amount_value = Decimal(amount)
        except (InvalidOperation, TypeError, ValueError):
            error_message = "Please enter a valid amount."
            if is_ajax:
                return JsonResponse(
                    {"success": False, "message": error_message},
                    status=400,
                )
            messages.error(request, error_message)
            return redirect("customer_order", shop_slug=shop.slug)

        if amount_value <= 0:
            error_message = "Please enter an amount greater than zero."
            if is_ajax:
                return JsonResponse(
                    {"success": False, "message": error_message},
                    status=400,
                )
            messages.error(request, error_message)
            return redirect("customer_order", shop_slug=shop.slug)

        item_key = str(menu_item.id)
        cart[item_key] = {
            "amount": str(amount_value),
            "quantity": 1,
        }

    request.session["cart"] = cart
    request.session.modified = True

    message = f"{menu_item.name} added to your cart."
    cart_count = sum(
        int(item.get("quantity", 0))
        for item in cart.values()
    )

    if is_ajax:
        return JsonResponse({
            "success": True,
            "message": message,
            "cart_count": cart_count,
        })

    messages.success(request, message)
    return redirect("customer_order", shop_slug=shop.slug)


def cart(request, shop_slug):

    shop = get_object_or_404(
        Shop,
        slug=shop_slug,
        is_active=True,
    )
    cart_data = request.session.get("cart", {})
    cart_items = []
    subtotal = Decimal("0.00")

    for cart_key, cart_item in cart_data.items():
        menu_id = str(cart_key).split("__", 1)[0]
        menu_item = MenuItem.objects.filter(
            id=menu_id,
            shop=shop,
            is_available=True,
        ).first()

        if not menu_item:
            continue
        if menu_item.price is None or menu_item.price < Decimal("45.00"):
            cart_data.pop(cart_key, None)
            request.session["cart"] = cart_data
            request.session.modified = True
            continue

        quantity = max(1, int(cart_item.get("quantity", 1)))
        extras = cart_item.get("extras", []) if shop.pk == 8 else []

        extras_base_total = sum(
            (Decimal(str(extra.get("base_price", "0.00"))) for extra in extras),
            Decimal("0.00"),
        )
        extras_customer_total = sum(
            (Decimal(str(extra.get("customer_price", "0.00"))) for extra in extras),
            Decimal("0.00"),
        )

        if menu_item.pricing_type == "fixed":
            shop_unit_price = menu_item.price or Decimal("0.00")
            customer_unit_price = (
                shop_unit_price * Decimal("1.25")
            ).quantize(Decimal("0.01"))
            shop_unit_total = shop_unit_price + extras_base_total
            customer_unit_total = customer_unit_price + extras_customer_total
            shop_line_total = shop_unit_total * quantity
            line_total = customer_unit_total * quantity

            cart_items.append({
                "cart_key": cart_key,
                "menu_item": menu_item,
                "quantity": quantity,
                "unit_price": customer_unit_total,
                "line_total": line_total,
                "shop_line_total": shop_line_total,
                "pricing_type": "fixed",
                "extras": extras,
            })
        else:
            shop_amount = Decimal(str(cart_item.get("amount", "0.00")))
            unit_price = (
                shop_amount * Decimal("1.25")
            ).quantize(Decimal("0.01"))
            line_total = unit_price
            shop_line_total = shop_amount

            cart_items.append({
                "cart_key": cart_key,
                "menu_item": menu_item,
                "quantity": 1,
                "unit_price": unit_price,
                "line_total": line_total,
                "shop_line_total": shop_line_total,
                "pricing_type": "amount",
                "extras": [],
            })

        subtotal += line_total

    context = {
        "shop": shop,
        "cart_items": cart_items,
        "subtotal": subtotal,
    }
    return render(request, "orders/cart.html", context)


def update_cart(request, shop_slug, menu_item_id):

    shop = get_object_or_404(Shop, slug=shop_slug, is_active=True)

    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request."}, status=400)

    cart = request.session.get("cart", {})
    item_key = str(menu_item_id)

    if item_key not in cart:
        return JsonResponse({"success": False, "message": "This item is no longer in your cart."}, status=404)

    menu_id = item_key.split("__", 1)[0]
    menu_item = get_object_or_404(
        MenuItem, id=menu_id, shop=shop, is_available=True
    )
    if menu_item.price is None or menu_item.price < Decimal("45.00"):
        cart.pop(item_key, None)
        request.session["cart"] = cart
        request.session.modified = True
        return JsonResponse(
            {"success": False, "message": "Items below R45 are no longer available."},
            status=400,
        )

    if menu_item.pricing_type != "fixed":
        return JsonResponse({
            "success": False,
            "message": "This item uses an amount instead of quantity.",
        }, status=400)

    try:
        quantity = int(request.POST.get("quantity", "1"))
    except (TypeError, ValueError):
        return JsonResponse({"success": False, "message": "Invalid quantity."}, status=400)

    if quantity < 1:
        cart.pop(item_key, None)
        request.session["cart"] = cart
        request.session.modified = True
        removed = True
        line_total = Decimal("0.00")
    else:
        cart[item_key]["quantity"] = quantity
        request.session["cart"] = cart
        request.session.modified = True
        removed = False

        extras = cart[item_key].get("extras", []) if shop.pk == 8 else []
        extras_customer_total = sum(
            (Decimal(str(extra.get("customer_price", "0.00"))) for extra in extras),
            Decimal("0.00"),
        )
        customer_unit_price = (
            (menu_item.price or Decimal("0.00")) * Decimal("1.25")
        ).quantize(Decimal("0.01")) + extras_customer_total
        line_total = customer_unit_price * quantity

    subtotal = Decimal("0.00")
    for cart_key, cart_item in cart.items():
        cart_menu_id = str(cart_key).split("__", 1)[0]
        cart_menu_item = MenuItem.objects.filter(
            id=cart_menu_id, shop=shop, is_available=True
        ).first()
        if not cart_menu_item:
            continue

        if cart_menu_item.pricing_type == "fixed":
            cart_quantity = max(1, int(cart_item.get("quantity", 1)))
            extras = cart_item.get("extras", []) if shop.pk == 8 else []
            extras_total = sum(
                (Decimal(str(extra.get("customer_price", "0.00"))) for extra in extras),
                Decimal("0.00"),
            )
            unit_price = (
                (cart_menu_item.price or Decimal("0.00")) * Decimal("1.25")
            ).quantize(Decimal("0.01")) + extras_total
            subtotal += unit_price * cart_quantity
        else:
            amount = Decimal(str(cart_item.get("amount", "0.00")))
            subtotal += (amount * Decimal("1.25")).quantize(Decimal("0.01"))

    cart_count = sum(max(0, int(item.get("quantity", 0))) for item in cart.values())

    return JsonResponse({
        "success": True,
        "removed": removed,
        "quantity": 0 if removed else quantity,
        "line_total": f"{line_total:.2f}",
        "subtotal": f"{subtotal:.2f}",
        "cart_count": cart_count,
    })


def remove_from_cart(request, shop_slug, menu_item_id):

    shop = get_object_or_404(Shop, slug=shop_slug, is_active=True)

    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request."}, status=400)

    cart = request.session.get("cart", {})
    item_key = str(menu_item_id)

    if item_key not in cart:
        return JsonResponse({"success": False, "message": "This item is already removed."}, status=404)

    menu_id = item_key.split("__", 1)[0]
    if not MenuItem.objects.filter(
        id=menu_id, shop=shop
    ).exists():
        return JsonResponse({"success": False, "message": "Invalid cart item."}, status=404)

    cart.pop(item_key, None)
    request.session["cart"] = cart
    request.session.modified = True

    subtotal = Decimal("0.00")
    for cart_key, cart_item in cart.items():
        cart_menu_id = str(cart_key).split("__", 1)[0]
        cart_menu_item = MenuItem.objects.filter(
            id=cart_menu_id, shop=shop, is_available=True
        ).first()
        if not cart_menu_item:
            continue

        if cart_menu_item.pricing_type == "fixed":
            quantity = max(1, int(cart_item.get("quantity", 1)))
            extras = cart_item.get("extras", []) if shop.pk == 8 else []
            extras_total = sum(
                (Decimal(str(extra.get("customer_price", "0.00"))) for extra in extras),
                Decimal("0.00"),
            )
            unit_price = (
                (cart_menu_item.price or Decimal("0.00")) * Decimal("1.25")
            ).quantize(Decimal("0.01")) + extras_total
            subtotal += unit_price * quantity
        else:
            amount = Decimal(str(cart_item.get("amount", "0.00")))
            subtotal += (amount * Decimal("1.25")).quantize(Decimal("0.01"))

    cart_count = sum(max(0, int(item.get("quantity", 0))) for item in cart.values())

    return JsonResponse({
        "success": True,
        "cart_count": cart_count,
        "subtotal": f"{subtotal:.2f}",
    })

def checkout(request, shop_slug):

    shop = get_object_or_404(
        Shop,
        slug=shop_slug,
        is_active=True,
    )

    cart_data = request.session.get("cart", {})
    cart_items = []
    subtotal = Decimal("0.00")

    for cart_key, cart_item in list(cart_data.items()):

        menu_id = str(cart_key).split("__", 1)[0]
        menu_item = MenuItem.objects.filter(
            id=menu_id,
            shop=shop,
            is_available=True,
        ).first()

        if not menu_item:
            continue
        if menu_item.price is None or menu_item.price < Decimal("45.00"):
            cart_data.pop(cart_key, None)
            request.session["cart"] = cart_data
            request.session.modified = True
            continue

        quantity = max(1, int(cart_item.get("quantity", 1)))
        extras = cart_item.get("extras", []) if shop.pk == 8 else []

        extras_base_total = sum(
            (Decimal(str(extra.get("base_price", "0.00"))) for extra in extras),
            Decimal("0.00"),
        )
        extras_customer_total = sum(
            (Decimal(str(extra.get("customer_price", "0.00"))) for extra in extras),
            Decimal("0.00"),
        )

        if menu_item.pricing_type == "fixed":
            shop_unit_price = menu_item.price or Decimal("0.00")
            customer_unit_price = (
                shop_unit_price * Decimal("1.25")
            ).quantize(Decimal("0.01"))
            shop_unit_total = shop_unit_price + extras_base_total
            customer_unit_total = customer_unit_price + extras_customer_total
            shop_line_total = shop_unit_total * quantity
            line_total = customer_unit_total * quantity
        else:
            shop_unit_price = Decimal(str(cart_item.get("amount", "0.00")))
            customer_unit_total = (
                shop_unit_price * Decimal("1.25")
            ).quantize(Decimal("0.01"))
            quantity = 1
            shop_line_total = shop_unit_price
            line_total = customer_unit_total
            extras = []

        cart_items.append({
            "cart_key": cart_key,
            "menu_item": menu_item,
            "quantity": quantity,
            "unit_price": customer_unit_total,
            "line_total": line_total,
            "shop_line_total": shop_line_total,
            "pricing_type": menu_item.pricing_type,
            "extras": extras,
        })

        subtotal += line_total

    if not cart_items:

        messages.warning(
            request,
            "Your cart is empty. Please add items before checkout.",
        )

        return redirect(
            "customer_order",
            shop_slug=shop.slug,
        )

    customer_name = ""
    whatsapp_number = ""
    delivery_address = ""
    notes = ""

    delivery_fee = None
    platform_fee = None
    total = subtotal
    delivery_distance_km = None
    customer_latitude = None
    customer_longitude = None
    price_calculated = False
    delivery_unavailable = False

    # =========================================================
    # RETURNING CUSTOMER MEMORY
    # Match by customer name + WhatsApp number and restore
    # the most recent delivery address.
    # =========================================================
    # =========================================================
    # LOGGED-IN CUSTOMER IDENTITY
    # Use the registered CustomerProfile details as the
    # authoritative checkout identity.
    # =========================================================
    if request.user.is_authenticated and hasattr(
        request.user,
        "customer_profile",
    ):
        customer_name = request.user.first_name.strip()
        whatsapp_number = (
            request.user.customer_profile.whatsapp_number.strip()
        )
    if request.method == "GET":
        saved_customer_name = request.session.get(
            "airxpress_customer_name",
            "",
        ).strip()

        saved_whatsapp_number = request.session.get(
            "airxpress_customer_whatsapp",
            "",
        ).strip()

        if saved_customer_name and saved_whatsapp_number:
            previous_order = (
                Order.objects
                .filter(
                    customer_name__iexact=saved_customer_name,
                    whatsapp_number=saved_whatsapp_number,
                    delivery_address__isnull=False,
                )
                .exclude(
                    delivery_address="",
                )
                .order_by("-created_at")
                .first()
            )

            if previous_order:
                customer_name = previous_order.customer_name
                whatsapp_number = previous_order.whatsapp_number
                delivery_address = previous_order.delivery_address

    if request.method == "POST":

        # Always use the registered account details for checkout.
        # Do not trust editable POST identity fields for logged-in customers.
        if request.user.is_authenticated and hasattr(
            request.user,
            "customer_profile",
        ):
            customer_name = request.user.first_name.strip()
            whatsapp_number = (
                request.user.customer_profile.whatsapp_number.strip()
            )
        else:
            customer_name = request.POST.get(
                "customer_name",
                "",
            ).strip()

            whatsapp_number = request.POST.get(
                "whatsapp_number",
                "",
            ).strip()

        delivery_address = request.POST.get(
            "delivery_address",
            "",
        ).strip()

        # Remember the customer identity for future orders.
        request.session["airxpress_customer_name"] = customer_name
        request.session["airxpress_customer_whatsapp"] = whatsapp_number
        request.session.modified = True

        notes = request.POST.get(
            "notes",
            ""
        ).strip()

        action = request.POST.get(
            "checkout_action",
            "calculate",
        )

        if not customer_name:

            messages.error(
                request,
                "Please enter your name.",
            )

        elif not whatsapp_number:

            messages.error(
                request,
                "Please enter your WhatsApp or contact number.",
            )

        elif not delivery_address:

            messages.error(
                request,
                "Please enter your delivery address.",
            )

        elif shop.latitude is None or shop.longitude is None:

            messages.error(
                request,
                "Delivery availability for this shop could not be verified just now. Please contact AirXpress Eats support for assistance.",
            )

        else:

            delivery_pricing = getattr(
                shop,
                "delivery_pricing",
                None,
            )

            if not delivery_pricing:

                messages.error(
                    request,
                    "Delivery pricing has not been configured for this shop yet.",
                )

            else:

                try:

                    confirmed_latitude_raw = request.POST.get(
                        "confirmed_latitude", ""
                    ).strip()
                    confirmed_longitude_raw = request.POST.get(
                        "confirmed_longitude", ""
                    ).strip()

                    if confirmed_latitude_raw or confirmed_longitude_raw:
                        if not confirmed_latitude_raw or not confirmed_longitude_raw:
                            raise MapboxError(
                                "Please confirm your delivery pin again."
                            )

                        try:
                            confirmed_latitude = Decimal(
                                confirmed_latitude_raw
                            )
                            confirmed_longitude = Decimal(
                                confirmed_longitude_raw
                            )
                        except (InvalidOperation, ValueError):
                            raise MapboxError(
                                "The selected map location is invalid."
                            )

                        if not (
                            Decimal("-90") <= confirmed_latitude <= Decimal("90")
                            and Decimal("-180") <= confirmed_longitude <= Decimal("180")
                        ):
                            raise MapboxError(
                                "The selected map location is outside valid coordinates."
                            )

                        route = calculate_driving_distance_to_coordinates(
                            shop.latitude,
                            shop.longitude,
                            confirmed_latitude,
                            confirmed_longitude,
                        )
                    else:
                        route = calculate_driving_distance(
                            shop.latitude,
                            shop.longitude,
                            delivery_address,
                        )

                    parsed_distance = Decimal(
                        str(route["distance_km"])
                    )

                    customer_latitude = Decimal(
                        str(route["customer_latitude"])
                    )

                    customer_longitude = Decimal(
                        str(route["customer_longitude"])
                    )

                except MapboxError:
                    messages.error(
                        request,
                        (
                            "Address verification failed. "
                            "We could not confirm this delivery address in the "
                            "suburb/locality you entered. "
                            "Please check your house number, street name, "
                            "extension/suburb and city, then try again."
                        ),
                    )

                else:

                    if parsed_distance <= 0:
                        messages.error(
                            request,
                            "We could not calculate a valid delivery distance. Please check your address.",
                        )
                    elif parsed_distance > delivery_pricing.max_radius_km:
                        delivery_unavailable = True
                        messages.error(
                            request,
                            (
                                "Delivery for this shop is currently unavailable "
                                "in your area. We're sorry for the inconvenience. "
                                "Please try another shop available in your area "
                                "or contact AirXpress Eats support for assistance."
                            ),
                        )
                    else:
                        matching_rate = (
                            delivery_pricing.rates
                            .filter(max_distance_km__gte=parsed_distance)
                            .order_by("max_distance_km")
                            .first()
                        )

                        if matching_rate is None:
                            delivery_unavailable = True
                            messages.error(
                                request,
                                "Delivery availability for this shop could not be verified just now. Please contact AirXpress Eats support for assistance.",
                            )
                        else:
                            delivery_fee = matching_rate.delivery_fee
                            platform_fee = Decimal("0.00")
                            driver_payout = (
                                delivery_fee
                                * delivery_pricing.driver_percentage
                                / Decimal("100.00")
                            ).quantize(Decimal("0.01"))

                            total = subtotal + delivery_fee
                            delivery_distance_km = parsed_distance
                            price_calculated = True

                            if action == "confirm":

                                order = Order.objects.create(
                                    shop=shop,
                                    customer_name=customer_name,
                                    whatsapp_number=whatsapp_number,
                                    delivery_address=delivery_address,
                                    order_type="delivery",
                                    order_source="online",
                                    status="new",
                                    estimated_total=subtotal,
                                    delivery_fee=delivery_fee,
                                    delivery_distance_km=parsed_distance,
                                    customer_latitude=customer_latitude,
                                    customer_longitude=customer_longitude,
                                    final_total=total,
                                    platform_fee=platform_fee,
                                    driver_payout=driver_payout,
                                    payment_status="pending",
                                    notes=notes,
                                )

                                for item in cart_items:

                                    OrderItem.objects.create(
                                        order=order,
                                        menu_item=item["menu_item"],
                                        requested_amount=item["line_total"],
                                        shop_amount=item["shop_line_total"],
                                        quantity=item["quantity"],
                                        unit_price=(
                                            item["unit_price"]
                                            if item["pricing_type"] == "fixed"
                                            else None
                                        ),
                                        extras=item.get("extras", []),
                                    )

                                OrderStatusHistory.objects.create(
                                    order=order,
                                    status="new",
                                    notes=(
                                        "Customer confirmed the complete "
                                        "food, delivery and AirXpress total "
                                        "at checkout."
                                    ),
                                )

                                request.session["cart"] = {}
                                request.session.modified = True

                                return redirect(
                                    "payfast_payment",
                                    order_id=order.id,
                                )


                            messages.success(
                                request,
                                (
                                    "Delivery calculated successfully. "
                                    "Please review and confirm your complete order total."
                                ),
                            )


        # =========================================================
    context = {
        "shop": shop,
        "cart_items": cart_items,
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "platform_fee": platform_fee,
        "total": total,
        "customer_name": customer_name,
        "whatsapp_number": whatsapp_number,
        "delivery_address": delivery_address,
        "notes": notes,
        "delivery_distance_km": delivery_distance_km,
        "price_calculated": price_calculated,
        "delivery_unavailable": delivery_unavailable,
    }

    return render(
        request,
        "orders/checkout.html",
        context,
    )
def airxpress_help(request):
    return render(
        request,
        "orders/airxpress_help.html",
        {
            "support_phone_display": "081 570 2241",
            "support_phone_tel": "+27815702241",
            "support_whatsapp": "27815702241",
        },
    )

def submit_support_ticket(request):
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "message": "POST is required."},
            status=405,
        )

    description = request.POST.get("description", "").strip()
    subject = request.POST.get("subject", "").strip()
    category = request.POST.get("category", "general").strip().lower()
    customer_name = request.POST.get("customer_name", "").strip()
    customer_phone = request.POST.get("customer_phone", "").strip()

    if not description or len(description) > 5000:
        return JsonResponse(
            {"success": False, "message": "Describe your issue in 1-5000 characters."},
            status=400,
        )

    if category not in {"technical", "operations", "general"}:
        category = "general"

    if not subject:
        subject = description[:200]

    text = f"{subject} {description}".lower()

    critical_terms = (
        "whole site down", "entire site down", "website is down",
        "site is down", "all orders blocked", "nobody can order",
        "no one can order", "everyone cannot order", "system completely down",
        "all checkout failing", "all users affected",
    )
    high_terms = (
        "checkout failing", "checkout not working", "cannot checkout",
        "can't checkout", "cannot place order", "can't place order",
        "orders not going through", "shop cannot accept orders",
        "shop can't accept orders", "delivery blocked", "driver cannot accept",
        "payment failing", "payment not working", "multiple customers",
    )

    if any(term in text for term in critical_terms):
        priority = "critical"
        assigned_team = "both"
    elif any(term in text for term in high_terms):
        priority = "high"
        assigned_team = (
            "technical" if category == "technical"
            else "operations" if category == "operations"
            else "general"
        )
    else:
        priority = "normal"
        assigned_team = (
            "technical" if category == "technical"
            else "operations" if category == "operations"
            else "general"
        )

    requires_escalation = (
        priority == "critical"
        or (priority == "high" and assigned_team in {"technical", "both"})
    )

    if priority == "critical":
        escalation_notes = (
            "Critical incident: flagged for both teams; prioritise during support hours. After-hours response is optional."
        )
    elif requires_escalation:
        escalation_notes = (
            "High-priority technical issue: review during support hours."
        )
    else:
        escalation_notes = ""

    ticket = SupportTicket.objects.create(
        customer=request.user if request.user.is_authenticated else None,
        customer_name=customer_name[:150],
        customer_phone=customer_phone[:30],
        category=category,
        subject=subject[:200],
        description=description,
        priority=priority,
        assigned_team=assigned_team,
        requires_escalation=requires_escalation,
        escalation_notes=escalation_notes,
        status="open",
    )

    if priority == "critical":
        reply = (
            "Your report has been saved as a CRITICAL incident and flagged for "
            "both technical and operations teams. If the service is completely "
            "unavailable, contact Technical Support on 073 314 1222 and "
            "Operations on 081 570 2241."
        )
    elif priority == "high":
        reply = (
            "Your report has been saved as a HIGH-priority ticket. The relevant "
            "team will need to investigate. You can also contact Technical "
            "Support on 073 314 1222 or Operations on 081 570 2241."
        )
    else:
        if category == "general":
            reply = (
                "Your enquiry has been received and saved. The AirXpress team "
                "will review it. Please keep your ticket reference for follow-up."
            )
        elif category == "operations":
            reply = (
                "Your request has been saved for the Operations team to review. "
                "Please keep your ticket reference for follow-up."
            )
        else:
            reply = (
                "Your technical report has been saved for review. Please keep "
                "your ticket reference for follow-up. If the service is completely "
                "unavailable, contact Technical Support on 073 314 1222."
            )

    return JsonResponse({
        "success": True,
        "reference": str(ticket.reference)[:8].upper(),
        "priority": ticket.priority,
        "assigned_team": ticket.assigned_team,
        "message": reply,
    })

def login_gateway(request):
    return render(request, "orders/login.html")


@require_POST
@login_required(login_url="/customer/login/")
def customer_keep_alive(request):
    """Extend an authenticated customer's session after explicit confirmation."""
    import time

    user = request.user

    if user.is_staff or user.is_superuser:
        return JsonResponse({"ok": False}, status=403)

    try:
        user.customer_profile
    except Exception:
        return JsonResponse({"ok": False}, status=403)

    request.session["airxpress_customer_last_activity"] = int(time.time())
    request.session.set_expiry(10 * 60)

    return JsonResponse({"ok": True, "expires_in": 600})


def customer_login(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(
                request,
                user,
                backend="django.contrib.auth.backends.ModelBackend",
            )

            if hasattr(user, "customer_profile"):
                request.session["airxpress_customer_name"] = user.first_name
                request.session["airxpress_customer_whatsapp"] = user.customer_profile.whatsapp_number
                request.session.modified = True

            if hasattr(user, "customer_profile") and user.customer_profile.must_change_password:
                return redirect("customer_change_password")
            return redirect("home")

        messages.error(request, "Invalid username or password.")

    return render(request, "orders/customer_login.html")

@login_required(login_url="/customer/login/")
def customer_change_password(request):
    """Require a customer using a temporary password to choose a new one."""
    if not hasattr(request.user, "customer_profile"):
        messages.error(request, "This page is only for customer accounts.")
        return redirect("home")

    profile = request.user.customer_profile

    if request.method == "POST":
        new_password = request.POST.get("new_password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if not new_password or new_password != confirm_password:
            messages.error(request, "The passwords are empty or do not match.")
            return render(
                request,
                "orders/customer_change_password.html",
            )

        try:
            validate_password(new_password, user=request.user)
        except ValidationError as exc:
            for error in exc.messages:
                messages.error(request, error)
            return render(
                request,
                "orders/customer_change_password.html",
            )

        request.user.set_password(new_password)
        request.user.save(update_fields=["password"])

        profile.must_change_password = False
        profile.save(update_fields=["must_change_password"])

        update_session_auth_hash(request, request.user)
        messages.success(request, "Your password has been changed successfully.")

        return redirect("home")

    return render(
        request,
        "orders/customer_change_password.html",
    )

def customer_register(request):
    from .forms import CustomerRegistrationForm

    if request.method == "POST":
        form = CustomerRegistrationForm(request.POST)

        if request.POST.get("accept_terms") != "on":
            messages.error(
                request,
                "You must agree to the AirXpress Eats Terms and Conditions before creating an account.",
            )
        elif form.is_valid():
            user = form.save()

            login(
                request,
                user,
                backend="django.contrib.auth.backends.ModelBackend",
            )

            request.session["airxpress_customer_name"] = (
                user.first_name
            )

            request.session["airxpress_customer_whatsapp"] = (
                user.customer_profile.whatsapp_number
            )

            request.session.modified = True

            messages.success(
                request,
                "Your AirXpress account has been created successfully.",
            )

            return redirect("home")
    else:
        form = CustomerRegistrationForm()

    return render(
        request,
        "orders/customer_register.html",
        {
            "form": form,
        },
    )

def customer_order(request, shop_slug):

    shop = get_object_or_404(
        Shop,
        slug=shop_slug,
        is_active=True,
    )

    preview_mode = (
        request.GET.get("preview") == "1"
        and shop.pk == 20
        and shop.name == "Mozeka & Sons Catering Services"
    )

    menu_queryset = MenuItem.objects.filter(shop=shop)
    if not preview_mode:
        menu_queryset = menu_queryset.filter(
            is_available=True,
            price__gte=Decimal("45.00"),
        )
# The Love of Alex: hide items without valid prices.
    if shop.pk == 5 and shop.name == "The Love of Alex":
        menu_queryset = menu_queryset.filter(
            price__isnull=False,
            price__gt=Decimal("45.00"),
        )

    menu_items = list(
        menu_queryset.select_related("category").order_by(
            "category__display_order",
            "category__name",
            "display_order",
            "name",
        )
    )
    for item in menu_items:
        item.customer_price = (
            (item.price or Decimal("0.00")) * Decimal("1.25")
        ).quantize(Decimal("0.01"))

    # Weekday headings for Mozeka & Sons only.
    if shop.pk == 20 and shop.name == "Mozeka & Sons Catering Services":
        for item in menu_items:
            if item.name.startswith("Thursday - "):
                item.menu_day = "Thursday Menu"
            elif item.name.startswith("Friday - "):
                item.menu_day = "Friday Menu"
            elif item.name.startswith("Saturday - "):
                item.menu_day = "Saturday Menu"
            elif item.name.startswith("Sunday Lunch - "):
                item.menu_day = "Sunday Lunch Menu"
            elif item.name.startswith("Monday - African Cuisine - "):
                item.menu_day = "Monday ? African Cuisine"
            else:
                item.menu_day = "Other Menu"

    # =====================================================
    # POST REQUEST
    # =====================================================

    # =========================================================
    # RETURNING CUSTOMER MEMORY
    # Match by customer name + WhatsApp number and restore
    # the most recent delivery address.
    # =========================================================
    # =========================================================
    # LOGGED-IN CUSTOMER IDENTITY
    # Use the registered CustomerProfile details as the
    # authoritative checkout identity.
    # =========================================================
    if request.user.is_authenticated and hasattr(
        request.user,
        "customer_profile",
    ):
        customer_name = request.user.first_name.strip()
        whatsapp_number = (
            request.user.customer_profile.whatsapp_number.strip()
        )
    if request.method == "GET":
        saved_customer_name = request.session.get(
            "airxpress_customer_name",
            "",
        ).strip()

        saved_whatsapp_number = request.session.get(
            "airxpress_customer_whatsapp",
            "",
        ).strip()

        if saved_customer_name and saved_whatsapp_number:
            previous_order = (
                Order.objects
                .filter(
                    customer_name__iexact=saved_customer_name,
                    whatsapp_number=saved_whatsapp_number,
                    delivery_address__isnull=False,
                )
                .exclude(
                    delivery_address="",
                )
                .order_by("-created_at")
                .first()
            )

            if previous_order:
                customer_name = previous_order.customer_name
                whatsapp_number = previous_order.whatsapp_number
                delivery_address = previous_order.delivery_address

    if request.method == "POST":

        form = CustomerOrderForm(
            request.POST,
            shop=shop,
        user=request.user,
        )

        if form.is_valid():

            order = form.save(
                commit=False
            )

            order.shop = shop
            order.order_source = "online"
            order.order_type = "delivery"
            order.status = "new"
            order.payment_status = "pending"
            order.estimated_total = Decimal(
                "0.00"
            )

            order.save()

            requested_total = Decimal(
                "0.00"
            )

            # =================================================
            # CREATE ORDER ITEMS
            # =================================================

            for menu_item in menu_items:

                # =============================================
                # CUSTOMER ENTERS RAND AMOUNT
                # =============================================

                if menu_item.pricing_type == "amount":

                    amount_value = request.POST.get(
                        f"amount_{menu_item.id}"
                    )

                    if not amount_value:
                        continue

                    try:

                        requested_amount = Decimal(
                            amount_value
                        )

                    except (
                        InvalidOperation,
                        TypeError,
                        ValueError,
                    ):

                        continue

                    if requested_amount <= 0:
                        continue

                    OrderItem.objects.create(
                        order=order,
                        menu_item=menu_item,
                        requested_amount=requested_amount,
                        quantity=1,
                        unit_price=None,
                    )

                    requested_total += (
                        requested_amount
                    )

                # =============================================
                # FIXED PRICE ITEM
                # =============================================

                elif menu_item.pricing_type == "fixed":

                    quantity_value = request.POST.get(
                        f"quantity_{menu_item.id}",
                        "0",
                    )

                    try:

                        quantity = int(
                            quantity_value
                        )

                    except (
                        TypeError,
                        ValueError,
                    ):

                        quantity = 0

                    if quantity <= 0:
                        continue

                    if menu_item.price is None:
                        continue

                    line_total = (
                        menu_item.price
                        * quantity
                    )

                    OrderItem.objects.create(
                        order=order,
                        menu_item=menu_item,
                        requested_amount=line_total,
                        quantity=quantity,
                        unit_price=menu_item.price,
                    )

                    requested_total += (
                        line_total
                    )

            # =================================================
            # PREVENT EMPTY ORDERS
            # =================================================

            if not order.items.exists():

                order.delete()

                form.add_error(
                    None,
                    "Please select at least one item."
                )

            # =================================================
            # SAVE VALID ORDER
            # =================================================

            else:

                order.estimated_total = (
                    requested_total
                )

                order.save(
                    update_fields=[
                        "estimated_total"
                    ]
                )

                OrderStatusHistory.objects.create(
                    order=order,
                    status="new",
                    notes="Customer placed order.",
                )

                return redirect(
                    "order_success",
                    shop_slug=shop.slug,
                    order_id=order.id,
                )

    # =====================================================
    # GET REQUEST
    # =====================================================

    else:

        form = CustomerOrderForm(
            shop=shop,
            user=request.user,
        )

    # =====================================================
    # PAGE CONTEXT
    # =====================================================


    # =========================================================
    context = {
        "shop": shop,
        "form": form,
        "menu_items": menu_items,
        "preview_mode": preview_mode,
        "extras_options": [
            {
                "id": extra_id,
                "name": name,
                "base_price": base_price,
                "customer_price": (base_price * Decimal("1.25")).quantize(Decimal("0.01")),
            }
            for extra_id, name, base_price in NALEDI_EXTRAS_CATALOG
        ] if shop.pk == 8 else [],
    }

    return render(
        request,
        "orders/customer_order.html",
        context,
    )


# =========================================================
# ORDER SUCCESS PAGE
# =========================================================

def order_success(request, shop_slug, order_id):
    shop = get_object_or_404(
        Shop,
        slug=shop_slug,
        is_active=True,
    )

    order = get_object_or_404(
        Order.objects
        .select_related("shop", "driver")
        .prefetch_related("items__menu_item"),
        id=order_id,
        shop=shop,
    )

    return render(
        request,
        "orders/order_success.html",
        {
            "shop": shop,
            "order": order,
        },
    )

@login_required(login_url="/customer/login/")
def customer_banking_details(request):
    """
    Display and update the logged-in customer's banking details.
    """

    if not hasattr(request.user, "customer_profile"):
        messages.error(
            request,
            "Your customer profile could not be found.",
        )
        return redirect("customer_login")

    profile = request.user.customer_profile

    if request.method == "POST":
        profile.bank_name = request.POST.get("bank_name", "").strip()
        profile.account_holder_name = request.POST.get(
            "account_holder_name",
            "",
        ).strip()
        if request.POST.get("change_account_number") == "1":
            new_account_number = request.POST.get(
                "account_number",
                "",
            ).strip()

            if new_account_number:
                profile.account_number = new_account_number
        profile.account_type = request.POST.get(
            "account_type",
            "",
        ).strip()
        profile.branch_code = request.POST.get(
            "branch_code",
            "",
        ).strip()

        profile.save()

        messages.success(
            request,
            "Your banking details have been saved successfully.",
        )

        return redirect("customer_banking_details")

    return render(
        request,
        "orders/customer_banking_details.html",
        {
            "profile": profile,
        },
    )


@login_required
def customer_my_orders(request):
    """
    Display the logged-in customer's orders across all shops.
    Customers are matched using their account name and WhatsApp number.
    """

    if not hasattr(request.user, "customer_profile"):
        messages.error(
            request,
            "Your customer profile could not be found.",
        )
        return redirect("customer_login")

    customer_name = request.user.first_name.strip()
    whatsapp_number = request.user.customer_profile.whatsapp_number.strip()

    orders = (
        Order.objects
        .filter(
            customer_name__iexact=customer_name,
            whatsapp_number=whatsapp_number,
        )
        .select_related(
            "shop",
            "driver",
        )
        .prefetch_related(
            "items__menu_item",
        )
        .order_by(
            "-created_at",
        )
    )

    return render(
        request,
        "orders/customer_my_orders.html",
        {
            "orders": orders,
            "customer_name": customer_name,
            "whatsapp_number": whatsapp_number,
        },
    )


@login_required(login_url='/customer/login/')
def customer_refund_enquiry(request):
    """Let a customer select one paid order for a refund enquiry."""
    if not hasattr(request.user, "customer_profile"):
        messages.error(request, "Your customer profile could not be found.")
        return redirect("customer_login")

    customer_name = request.user.first_name.strip()
    whatsapp_number = request.user.customer_profile.whatsapp_number.strip()

    orders = list(
        Order.objects.filter(
            customer_name__iexact=customer_name,
            whatsapp_number=whatsapp_number,
            payment_status="paid",
            final_total__gt=Decimal("0.00"),
        )
        .select_related("shop")
        .order_by("-created_at")
    )

    active_statuses = ["pending", "under_review", "approved", "paid"]
    can_select_order = False

    for order in orders:
        order.refund_enquiry_exists = RefundRequest.objects.filter(
            order=order,
            status__in=active_statuses,
        ).exists()
        if not order.refund_enquiry_exists:
            can_select_order = True

    selected_id = request.GET.get("order_id", "").strip()

    if selected_id:
        if not selected_id.isdigit():
            messages.error(request, "Please select a valid order.")
            return redirect("customer_refund_enquiry")

        order = get_object_or_404(
            Order.objects.select_related("shop"),
            id=int(selected_id),
            customer_name__iexact=customer_name,
            whatsapp_number=whatsapp_number,
            payment_status="paid",
            final_total__gt=Decimal("0.00"),
        )

        if RefundRequest.objects.filter(
            order=order,
            status__in=active_statuses,
        ).exists():
            messages.info(
                request,
                "An active refund request already exists for that order.",
            )
            return redirect("customer_refund_enquiry")

        return redirect("customer_refund_request", order_id=order.id)

    return render(
        request,
        "orders/customer_refund_enquiry.html",
        {
            "orders": orders,
            "can_select_order": can_select_order,
        },
    )


@login_required(login_url='/customer/login/')
def customer_refund_request(request, order_id):
    if not hasattr(request.user, 'customer_profile'):
        messages.error(request, 'Your customer profile could not be found.')
        return redirect('customer_login')

    customer_name = request.user.first_name.strip()
    whatsapp_number = request.user.customer_profile.whatsapp_number.strip()

    order = get_object_or_404(
        Order.objects.select_related('shop'),
        id=order_id,
        customer_name__iexact=customer_name,
        whatsapp_number=whatsapp_number,
    )

    if order.payment_status != 'paid':
        messages.error(request, 'Only orders with confirmed payment can be submitted for a refund.')
        return redirect('customer_my_orders')

    amount = order.final_total
    if amount is None or amount <= Decimal('0.00'):
        messages.error(request, 'This order does not have a valid confirmed payment amount.')
        return redirect('customer_my_orders')

    active_statuses = ['pending', 'under_review', 'approved', 'paid']

    if RefundRequest.objects.filter(
        order=order,
        status__in=active_statuses,
    ).exists():
        messages.info(request, 'A refund request already exists for this order.')
        return redirect('customer_my_orders')

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        raw_amount = request.POST.get('requested_amount', '').strip()

        if not reason:
            messages.error(request, 'Please provide a reason for the refund request.')
        elif len(reason) > 5000:
            messages.error(request, 'Your reason must be 5,000 characters or fewer.')
        else:
            try:
                requested_amount = Decimal(raw_amount)
            except (InvalidOperation, ValueError):
                requested_amount = Decimal('0.00')

            if not requested_amount.is_finite() or requested_amount <= Decimal('0.00'):
                messages.error(request, 'Enter a valid refund amount greater than zero.')
            elif requested_amount > amount:
                messages.error(request, 'The requested refund cannot exceed the confirmed order total.')
            else:
                with transaction.atomic():
                    existing = RefundRequest.objects.filter(
                        order=order,
                        status__in=active_statuses,
                    ).exists()

                    if existing:
                        messages.info(request, 'A refund request already exists for this order.')
                    else:
                        RefundRequest.objects.create(
                            order=order,
                            customer=request.user,
                            reason=reason,
                            requested_amount=requested_amount.quantize(Decimal('0.01')),
                        )
                        messages.success(request, 'Your refund request has been submitted for staff review.')
                        return redirect('customer_my_orders')

    return render(request, 'orders/customer_refund_request.html', {
        'order': order,
        'maximum_refund_amount': amount,
    })

def order_review(request, order_id):
    """
    Allow the logged-in customer to review a completed order.
    """

    if not hasattr(request.user, "customer_profile"):
        messages.error(
            request,
            "Your customer profile could not be found.",
        )
        return redirect("customer_login")

    customer_name = request.user.first_name.strip()
    whatsapp_number = (
        request.user.customer_profile.whatsapp_number.strip()
    )

    order = get_object_or_404(
        Order.objects
        .select_related("shop", "driver"),
        id=order_id,
        customer_name__iexact=customer_name,
        whatsapp_number=whatsapp_number,
    )

    if order.status not in ["delivered", "collected"]:
        messages.error(
            request,
            "This order is not completed yet and cannot be reviewed.",
        )
        return redirect(
            "track_order",
            tracking_token=order.tracking_token,
        )

    if hasattr(order, "review"):
        messages.info(
            request,
            "You have already reviewed this order.",
        )
        return redirect(
            "track_order",
            tracking_token=order.tracking_token,
        )

    if request.method == "POST":
        overall_rating = request.POST.get("overall_rating")
        food_rating = request.POST.get("food_rating")
        delivery_rating = request.POST.get("delivery_rating")
        comment = request.POST.get("comment", "").strip()

        try:
            overall_rating = int(overall_rating)
            food_rating = int(food_rating)
            delivery_rating = int(delivery_rating)
        except (TypeError, ValueError):
            messages.error(
                request,
                "Please select a valid rating.",
            )
            return render(
                request,
                "orders/order_review.html",
                {"order": order},
            )

        if not all(
            rating in [1, 2, 3, 4, 5]
            for rating in [
                overall_rating,
                food_rating,
                delivery_rating,
            ]
        ):
            messages.error(
                request,
                "Please select a rating from 1 to 5 stars.",
            )
            return render(
                request,
                "orders/order_review.html",
                {"order": order},
            )

        OrderReview.objects.create(
            order=order,
            customer=request.user,
            shop=order.shop,
            driver=order.driver,
            overall_rating=overall_rating,
            food_rating=food_rating,
            delivery_rating=delivery_rating,
            comment=comment,
        )

        return render(
            request,
            "orders/order_review_thank_you.html",
            {"order": order},
        )

    return render(
        request,
        "orders/order_review.html",
        {"order": order},
    )

def _build_delivery_qr_data_uri(order):
    """
    Build the customer's delivery QR locally.
    The QR contains only the order's random delivery token.
    """
    if (
        order.status not in ("driver_assigned", "picked_up", "delivered")
        or order.delivery_qr_verified_at is not None
    ):
        return ""

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=4,
    )
    qr.add_data(str(order.delivery_qr_token))
    qr.make(fit=True)

    image = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def track_order(request, tracking_token):
    order = get_object_or_404(
        Order.objects
        .select_related("shop", "driver")
        .prefetch_related("items__menu_item"),
        tracking_token=tracking_token,
    )

    return render(
        request,
        "orders/track_order.html",
        {
            "order": order,
            "shop": order.shop,
            "mapbox_token": settings.MAPBOX_TOKEN,
            "delivery_qr_data_uri": _build_delivery_qr_data_uri(order),
        },
    )


def track_order_status(request, tracking_token):
    order = get_object_or_404(
        Order.objects.select_related("shop", "driver"),
        tracking_token=tracking_token,
    )

    driver_latitude = (
        float(order.driver_latitude)
        if order.driver_latitude is not None
        else None
    )

    driver_longitude = (
        float(order.driver_longitude)
        if order.driver_longitude is not None
        else None
    )

    history = [
        {
            "status": entry.status,
            "status_display": entry.get_status_display(),
            "notes": entry.notes,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }
        for entry in order.status_history.all()
    ]

    return JsonResponse(
        {
            "history": history,
            "status": order.status,
            "status_display": order.get_status_display(),

            "driver": (
                order.driver.name
                if order.driver
                else ""
            ),

            "driver_name": (
                order.driver.name
                if order.driver
                else ""
            ),

            "driver_phone": "",
            "driver_photo": (
                order.driver.photo.url
                if order.driver and order.driver.photo
                else ""
            ),
            "vehicle_make_model": (
                order.driver.vehicle_make_model
                if order.driver
                else ""
            ),
            "vehicle_colour": (
                order.driver.vehicle_colour
                if order.driver
                else ""
            ),
            "vehicle_registration": (
                order.driver.vehicle_registration
                if order.driver
                else ""
            ),

            "customer_location": {
                "latitude": (
                    float(order.customer_latitude)
                    if order.customer_latitude is not None
                    else None
                ),
                "longitude": (
                    float(order.customer_longitude)
                    if order.customer_longitude is not None
                    else None
                ),
            },

            "driver_location": {
                "latitude": driver_latitude,
                "longitude": driver_longitude,
                "updated_at": (
                    order.driver_location_updated_at.isoformat()
                    if order.driver_location_updated_at
                    else None
                ),
            },

            "live_route": None,
        }
    )

def calculate_distance_km(
    latitude1,
    longitude1,
    latitude2,
    longitude2,
):
    """
    Calculate the straight-line GPS distance between
    two coordinates and return the result in kilometres.
    """

    earth_radius_km = 6371.0

    lat1 = math.radians(float(latitude1))
    lon1 = math.radians(float(longitude1))
    lat2 = math.radians(float(latitude2))
    lon2 = math.radians(float(longitude2))

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(delta_lon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a),
    )

    return earth_radius_km * c

@user_passes_test(
    lambda user: (
        user.is_authenticated
        and hasattr(user, "driver_profile")
    ),
    login_url="/driver/login/",
)
def update_driver_location(request, order_id):

    if request.method != "POST":
        return JsonResponse(
            {
                "success": False,
                "error": "POST request required.",
            },
            status=405,
        )

    driver = request.user.driver_profile

    order = get_object_or_404(
        Order.objects.select_related(
            "driver",
            "shop",
        ),
        id=order_id,
    )

    # Only the driver assigned to this order may
    # send GPS coordinates for this order.
    if not order.driver or order.driver_id != driver.id:
        return JsonResponse(
            {
                "success": False,
                "error": "You are not assigned to this order.",
            },
            status=403,
        )

    # GPS is active while travelling to pickup
    # and while completing the delivery.
    if order.status not in (
        "driver_assigned",
        "picked_up",
    ):
        return JsonResponse(
            {
                "success": False,
                "error": "GPS tracking is not active for this order.",
            },
            status=400,
        )

    try:
        latitude = float(
            request.POST.get("latitude")
        )

        longitude = float(
            request.POST.get("longitude")
        )

    except (TypeError, ValueError):

        return JsonResponse(
            {
                "success": False,
                "error": "Invalid GPS coordinates.",
            },
            status=400,
        )

    if not -90 <= latitude <= 90:
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid latitude.",
            },
            status=400,
        )

    if not -180 <= longitude <= 180:
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid longitude.",
            },
            status=400,
        )

    order.driver_latitude = latitude
    order.driver_longitude = longitude
    order.driver_location_updated_at = timezone.now()

    order.save(
        update_fields=[
            "driver_latitude",
            "driver_longitude",
            "driver_location_updated_at",
            "updated_at",
        ]
    )

    response = {
        "success": True,
        "latitude": latitude,
        "longitude": longitude,
    }

    # While travelling to the shop, calculate the
    # driver's current distance from the pickup point.
    if (
        order.status == "driver_assigned"
        and order.shop
        and order.shop.latitude is not None
        and order.shop.longitude is not None
    ):

        distance_km = calculate_distance_km(
            latitude,
            longitude,
            order.shop.latitude,
            order.shop.longitude,
        )

        distance_metres = round(
            distance_km * 1000,
            1,
        )

        response["pickup_distance_km"] = round(
            distance_km,
            3,
        )

        response["pickup_distance_metres"] = (
            distance_metres
        )

        response["pickup_radius_metres"] = 250

        response["at_pickup"] = (
            distance_metres <= 250
        )

    return JsonResponse(response)

def customer_invoice(request, shop_slug, order_id):
    shop = get_object_or_404(
        Shop,
        slug=shop_slug,
        is_active=True,
    )

    order = get_object_or_404(
        Order.objects
        .select_related("shop", "driver")
        .prefetch_related("items__menu_item"),
        id=order_id,
        shop=shop,
    )

    food_subtotal = sum(
        (
            item.final_amount
            if item.final_amount is not None
            else item.requested_amount
            if item.requested_amount is not None
            else item.unit_price or 0
        )
        for item in order.items.all()
    )

    return render(
        request,
        "orders/customer_invoice.html",
        {
            "shop": shop,
            "order": order,
            "food_subtotal": food_subtotal,
        },
    )

def customer_order_history(request, shop_slug):
    """
    Display a customer's order history for a specific shop.

    Customers are identified using their name and WhatsApp/contact
    number stored in the session.
    """

    shop = get_object_or_404(
        Shop,
        slug=shop_slug,
        is_active=True,
    )

    customer_name = request.session.get(
        "airxpress_customer_name",
        "",
    ).strip()

    whatsapp_number = request.session.get(
        "airxpress_customer_whatsapp",
        "",
    ).strip()

    orders = Order.objects.none()

    if request.method == "POST":

        customer_name = request.POST.get(
            "customer_name",
            "",
        ).strip()

        whatsapp_number = request.POST.get(
            "whatsapp_number",
            "",
        ).strip()

        if not customer_name:

            messages.error(
                request,
                "Please enter your name.",
            )

        elif not whatsapp_number:

            messages.error(
                request,
                "Please enter your WhatsApp or contact number.",
            )

        else:

            request.session["airxpress_customer_name"] = (
                customer_name
            )

            request.session["airxpress_customer_whatsapp"] = (
                whatsapp_number
            )

            request.session.modified = True

            orders = (
                Order.objects
                .filter(
                    shop=shop,
                    customer_name__iexact=customer_name,
                    whatsapp_number=whatsapp_number,
                )
                .select_related(
                    "driver",
                )
                .prefetch_related(
                    "items__menu_item",
                )
                .order_by(
                    "-created_at",
                )
            )

    elif customer_name and whatsapp_number:

        orders = (
            Order.objects
            .filter(
                shop=shop,
                customer_name__iexact=customer_name,
                whatsapp_number=whatsapp_number,
            )
            .select_related(
                "driver",
            )
            .prefetch_related(
                "items__menu_item",
            )
            .order_by(
                "-created_at",
            )
        )

    return render(
        request,
        "orders/customer_order_history.html",
        {
            "shop": shop,
            "orders": orders,
            "customer_name": customer_name,
            "whatsapp_number": whatsapp_number,
        },
    )# =========================================================
# ACCESS CHECKS
# =========================================================

def get_staff_profile(user):

    if not user.is_authenticated:
        return None

    try:
        profile = user.staff_profile
    except StaffProfile.DoesNotExist:
        return None

    if not profile.is_active:
        return None

    if not profile.shop.is_active:
        return None

    return profile


def get_user_shop(user):

    profile = get_staff_profile(user)

    if profile is None:
        return None

    return profile.shop


def is_tenant_staff(user):

    profile = get_staff_profile(user)

    if profile is None:
        return False

    return profile.role in {
        "owner",
        "manager",
        "staff",
    }

def is_owner(user):

    return (
        user.is_authenticated
        and user.is_superuser
    )



# =========================================================
# DRIVER LOGIN
# =========================================================


@user_passes_test(is_owner, login_url="/owner/login/")
def owner_update_support_ticket(request, ticket_id):
    if request.method != "POST":
        return redirect("owner_support_dashboard")

    ticket = get_object_or_404(SupportTicket, id=ticket_id)
    new_status = request.POST.get("status", "").strip()
    staff_notes = request.POST.get("staff_notes", "").strip()
    customer_response = request.POST.get("customer_response", "").strip()

    if new_status not in {"open", "in_progress", "resolved"}:
        messages.error(request, "Invalid ticket status.")
        return redirect("owner_support_dashboard")

    if len(staff_notes) > 10000:
        messages.error(request, "Internal notes must be 10,000 characters or fewer.")
        return redirect("owner_support_dashboard")

    if len(customer_response) > 10000:
        messages.error(request, "Customer response must be 10,000 characters or fewer.")
        return redirect("owner_support_dashboard")

    ticket.status = new_status
    ticket.staff_notes = staff_notes
    ticket.customer_response = customer_response
    ticket.save(update_fields=[
        "status",
        "staff_notes",
        "customer_response",
        "resolved_at",
        "updated_at",
    ])

    messages.success(
        request,
        f"Support ticket {str(ticket.reference)[:8].upper()} updated successfully.",
    )
    return redirect("owner_support_dashboard")


@user_passes_test(is_owner, login_url="/owner/login/")
def owner_support_dashboard(request):
    tickets = SupportTicket.objects.all()

    status_filter = request.GET.get("status", "").strip()
    priority_filter = request.GET.get("priority", "").strip()

    if status_filter in {"open", "in_progress", "resolved"}:
        tickets = tickets.filter(status=status_filter)

    if priority_filter in {"normal", "high", "critical"}:
        tickets = tickets.filter(priority=priority_filter)

    tickets = tickets.order_by(
        models.Case(
            models.When(priority="critical", then=0),
            models.When(priority="high", then=1),
            default=2,
            output_field=models.IntegerField(),
        ),
        "-created_at",
    )

    from urllib.parse import quote
    from django.urls import reverse

    login_url = request.build_absolute_uri(reverse("customer_login"))

    for ticket in tickets:
        ticket.whatsapp_url = ""
        phone = "".join(
            character
            for character in (ticket.customer_phone or "")
            if character.isdigit()
        )

        if phone.startswith("0"):
            phone = "27" + phone[1:]
        elif not phone.startswith("27"):
            phone = ""

        if phone and len(phone) >= 11 and ticket.customer_response:
            message = (
                f"Hello {ticket.customer_name or 'there'}, "
                f"here is an update on your AirXpress Eats support ticket "
                f"{str(ticket.reference)[:8].upper()}. "
                f"Status: {ticket.get_status_display()}. "
                f"{ticket.customer_response}\n\n"
                f"Log in to your account here: {login_url}\n\n"
                f"Thank you, AirXpress Eats Support."
            )
            ticket.whatsapp_url = (
                f"https://wa.me/{phone}?text={quote(message)}"
            )

    context = {
        "tickets": tickets,
        "status_filter": status_filter,
        "priority_filter": priority_filter,
        "total_tickets": SupportTicket.objects.count(),
        "open_tickets": SupportTicket.objects.filter(status="open").count(),
        "in_progress_tickets": SupportTicket.objects.filter(
            status="in_progress"
        ).count(),
        "escalation_tickets": SupportTicket.objects.filter(
            requires_escalation=True
        ).exclude(status="resolved").count(),
        "critical_tickets": SupportTicket.objects.filter(
            priority="critical"
        ).exclude(status="resolved").count(),
    }

    return render(
        request,
        "orders/owner_support_dashboard.html",
        context,
    )

@user_passes_test(is_owner, login_url="/owner/login/")
def owner_refund_enquiries(request):
    """Platform management queue for customer refund enquiries."""

    refunds = (
        RefundRequest.objects
        .select_related("order", "customer", "reviewed_by")
        .order_by("-created_at")
    )

    status_filter = request.GET.get("status", "").strip()

    valid_statuses = {
        value for value, label in RefundRequest.STATUS_CHOICES
    }

    if status_filter in valid_statuses:
        refunds = refunds.filter(status=status_filter)

    for refund in refunds:
        refund.whatsapp_message = ""
        refund.whatsapp_url = ""

        phone = "".join(
            character
            for character in (refund.order.whatsapp_number or "")
            if character.isdigit()
        )

        if phone.startswith("0"):
            phone = "27" + phone[1:]
        elif phone.startswith("27"):
            pass
        elif phone:
            phone = ""

        if phone and refund.status in {"approved", "rejected"}:
            if refund.status == "rejected":
                message = (
                    f"Hello {refund.order.customer_name}, regarding your "
                    f"refund enquiry for Order #{refund.order_id} "
                    f"(Reference {refund.reference}), we regret to inform "
                    f"you that your refund request of "
                    f"R{refund.requested_amount:.2f} has been declined "
                    f"following our review. Please contact AirXpress Eats "
                    f"if you would like further clarification. Thank you."
                )
            else:
                message = (
                    f"Hello {refund.order.customer_name}, your refund request "
                    f"for Order #{refund.order_id} (Reference {refund.reference}) "
                    f"has been approved for R{refund.requested_amount:.2f}. "
                    f"We will update you once the refund payment has been "
                    f"completed. Thank you, AirXpress Eats."
                )

            from urllib.parse import quote
            refund.whatsapp_message = message
            refund.whatsapp_url = (
                f"https://wa.me/{phone}?text={quote(message)}"
            )

    context = {
        "refunds": refunds,
        "status_filter": status_filter,
        "status_choices": RefundRequest.STATUS_CHOICES,
        "total_refunds": RefundRequest.objects.count(),
        "pending_refunds": RefundRequest.objects.filter(
            status="pending"
        ).count(),
        "under_review_refunds": RefundRequest.objects.filter(
            status="under_review"
        ).count(),
        "approved_refunds": RefundRequest.objects.filter(
            status="approved"
        ).count(),
        "paid_refunds": RefundRequest.objects.filter(
            status="paid"
        ).count(),
    }

    return render(
        request,
        "orders/owner_refund_enquiries.html",
        context,
    )

def _get_refund_audit_events(request):
    """Return filtered refund audit events for history and CSV export."""

    events = RefundAuditLog.objects.select_related(
        "refund",
        "refund__order",
        "refund__customer",
        "performed_by",
    ).order_by("-created_at", "-id")

    status_filter = request.GET.get("status", "").strip()
    search_query = request.GET.get("q", "").strip()

    valid_statuses = {
        value for value, label in RefundRequest.STATUS_CHOICES
    }

    if status_filter in valid_statuses:
        events = events.filter(new_status=status_filter)
    else:
        status_filter = ""

    if search_query:
        from django.db.models import Q

        events = events.filter(
            Q(refund__reference__icontains=search_query)
            | Q(refund__order__customer_name__icontains=search_query)
            | Q(refund__order__whatsapp_number__icontains=search_query)
            | Q(refund__order_id__icontains=search_query)
            | Q(performed_by__username__icontains=search_query)
            | Q(performed_by__first_name__icontains=search_query)
            | Q(performed_by__last_name__icontains=search_query)
            | Q(notes__icontains=search_query)
            | Q(previous_status__icontains=search_query)
            | Q(new_status__icontains=search_query)
            | Q(event_type__icontains=search_query)
        )

    return events, status_filter, search_query


@user_passes_test(is_owner, login_url="/owner/login/")
def owner_refund_audit_history(request):
    """Show individual refund audit events to the owner."""

    events, status_filter, search_query = _get_refund_audit_events(request)

    context = {
        "audit_events": events,
        "status_filter": status_filter,
        "search_query": search_query,
        "status_choices": RefundRequest.STATUS_CHOICES,
        "total_audit_events": events.count(),
    }

    return render(
        request,
        "orders/owner_refund_audit_history.html",
        context,
    )


@user_passes_test(is_owner, login_url="/owner/login/")
def owner_export_refund_audit_csv(request):
    """Export filtered refund audit events as CSV."""

    import csv

    events, status_filter, search_query = _get_refund_audit_events(request)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        'attachment; filename="airxpress_refund_audit_history.csv"'
    )
    response.write("\ufeff")

    writer = csv.writer(response)
    writer.writerow([
        "Timestamp",
        "Refund Reference",
        "Order ID",
        "Customer",
        "WhatsApp Number",
        "Refund Amount",
        "Event Type",
        "Previous Status",
        "New Status",
        "Performed By",
        "Notes",
    ])

    for event in events.iterator():
        refund = event.refund
        order = refund.order
        actor = event.performed_by

        if actor:
            performed_by = actor.get_full_name().strip() or actor.username
        else:
            performed_by = "Unknown"

        writer.writerow([
            event.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            str(refund.reference),
            refund.order_id,
            order.customer_name,
            order.whatsapp_number,
            f"{refund.requested_amount:.2f}",
            event.get_event_type_display(),
            event.previous_status,
            event.new_status,
            performed_by,
            event.notes,
        ])

    return response

def owner_update_refund_enquiry(request, refund_id):
    """Update a refund enquiry using an authorised POST request."""

    if request.method != "POST":
        return redirect("owner_refund_enquiries")

    with transaction.atomic():
        refund = get_object_or_404(
            RefundRequest.objects.select_for_update(),
            id=refund_id,
        )

        previous_status = refund.status
        action = request.POST.get("action", "").strip()
        staff_notes = request.POST.get("staff_notes", "").strip()

        if len(staff_notes) > 5000:
            messages.error(request, "Internal notes must be 5,000 characters or fewer.")
            return redirect("owner_refund_enquiries")

        if action == "under_review":
            if refund.status != "pending":
                messages.error(request, "Only pending enquiries can be moved into review.")
                return redirect("owner_refund_enquiries")

            refund.status = "under_review"
            refund.reviewed_by = request.user
            refund.reviewed_at = timezone.now()

        elif action in {"approved", "rejected"}:
            if refund.status not in {"pending", "under_review"}:
                messages.error(request, "This enquiry has already received a decision.")
                return redirect("owner_refund_enquiries")

            if action == "rejected" and not staff_notes:
                messages.error(request, "Provide an internal reason before rejecting a refund.")
                return redirect("owner_refund_enquiries")

            refund.status = action
            refund.reviewed_by = request.user
            refund.reviewed_at = timezone.now()

        elif action == "paid":
            if refund.status != "approved":
                messages.error(request, "Only approved refunds can be marked as paid.")
                return redirect("owner_refund_enquiries")

            refund.status = "paid"
            refund.paid_at = timezone.now()

        else:
            messages.error(request, "Invalid refund action.")
            return redirect("owner_refund_enquiries")

        if staff_notes:
            refund.staff_notes = staff_notes

        refund.save()

        RefundAuditLog.objects.create(
            refund=refund,
            event_type="status_changed",
            previous_status=previous_status,
            new_status=refund.status,
            performed_by=request.user,
            notes=staff_notes or refund.staff_notes,
        )

    messages.success(
        request,
        f"Refund enquiry {str(refund.reference)[:8].upper()} updated successfully.",
    )
    return redirect("owner_refund_enquiries")

@user_passes_test(is_owner, login_url="/owner/login/")
def owner_mark_refund_notification_sent(request, refund_id):
    """Record that an owner has confirmed sending a refund notification."""

    if request.method != "POST":
        return redirect("owner_refund_enquiries")

    with transaction.atomic():
        refund = get_object_or_404(
            RefundRequest.objects.select_for_update(),
            id=refund_id,
        )

        if refund.status not in {"approved", "rejected"}:
            messages.error(
                request,
                "Only approved or rejected enquiries can have a notification recorded.",
            )
            return redirect("owner_refund_enquiries")

        if refund.notification_sent_at:
            messages.warning(
                request,
                "A notification has already been recorded for this enquiry.",
            )
            return redirect("owner_refund_enquiries")

        refund.notification_sent_at = timezone.now()
        refund.notification_sent_by = request.user
        refund.save(
            update_fields=[
                "notification_sent_at",
                "notification_sent_by",
                "updated_at",
            ]
        )

        RefundAuditLog.objects.create(
            refund=refund,
            event_type="notification_recorded",
            previous_status=refund.status,
            new_status=refund.status,
            performed_by=request.user,
            notes="Staff confirmed that the WhatsApp notification was sent.",
        )

    messages.success(
        request,
        f"WhatsApp notification recorded for refund {str(refund.reference)[:8].upper()}.",
    )
    return redirect("owner_refund_enquiries")

def driver_login(request):

    if request.user.is_authenticated:

        try:
            driver = request.user.driver_profile
        except Exception:
            driver = None

        if driver is not None:
            return redirect("driver_dashboard")

        logout(request)

    # =========================================================
    # RETURNING CUSTOMER MEMORY
    # Match by customer name + WhatsApp number and restore
    # the most recent delivery address.
    # =========================================================
    # =========================================================
    # LOGGED-IN CUSTOMER IDENTITY
    # Use the registered CustomerProfile details as the
    # authoritative checkout identity.
    # =========================================================
    if request.user.is_authenticated and hasattr(
        request.user,
        "customer_profile",
    ):
        customer_name = request.user.first_name.strip()
        whatsapp_number = (
            request.user.customer_profile.whatsapp_number.strip()
        )
    if request.method == "GET":
        saved_customer_name = request.session.get(
            "airxpress_customer_name",
            "",
        ).strip()

        saved_whatsapp_number = request.session.get(
            "airxpress_customer_whatsapp",
            "",
        ).strip()

        if saved_customer_name and saved_whatsapp_number:
            previous_order = (
                Order.objects
                .filter(
                    customer_name__iexact=saved_customer_name,
                    whatsapp_number=saved_whatsapp_number,
                    delivery_address__isnull=False,
                )
                .exclude(
                    delivery_address="",
                )
                .order_by("-created_at")
                .first()
            )

            if previous_order:
                customer_name = previous_order.customer_name
                whatsapp_number = previous_order.whatsapp_number
                delivery_address = previous_order.delivery_address

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is None:

            messages.error(
                request,
                "Incorrect username or password."
            )

        else:

            try:
                driver = user.driver_profile
            except Exception:
                driver = None

            if driver is not None:

                login(request, user)

                return redirect(
                    "driver_dashboard"
                )

            messages.error(
                request,
                "This account does not have driver access."
            )

    return render(
        request,
        "orders/driver_login.html",
    )


# =========================================================
# STAFF LOGIN
# =========================================================


def staff_login(request):

    if request.user.is_authenticated:

        if is_tenant_staff(request.user):
            return redirect("staff_dashboard")

        logout(request)

    # =========================================================
    # RETURNING CUSTOMER MEMORY
    # Match by customer name + WhatsApp number and restore
    # the most recent delivery address.
    # =========================================================
    # =========================================================
    # LOGGED-IN CUSTOMER IDENTITY
    # Use the registered CustomerProfile details as the
    # authoritative checkout identity.
    # =========================================================
    if request.user.is_authenticated and hasattr(
        request.user,
        "customer_profile",
    ):
        customer_name = request.user.first_name.strip()
        whatsapp_number = (
            request.user.customer_profile.whatsapp_number.strip()
        )
    if request.method == "GET":
        saved_customer_name = request.session.get(
            "airxpress_customer_name",
            "",
        ).strip()

        saved_whatsapp_number = request.session.get(
            "airxpress_customer_whatsapp",
            "",
        ).strip()

        if saved_customer_name and saved_whatsapp_number:
            previous_order = (
                Order.objects
                .filter(
                    customer_name__iexact=saved_customer_name,
                    whatsapp_number=saved_whatsapp_number,
                    delivery_address__isnull=False,
                )
                .exclude(
                    delivery_address="",
                )
                .order_by("-created_at")
                .first()
            )

            if previous_order:
                customer_name = previous_order.customer_name
                whatsapp_number = previous_order.whatsapp_number
                delivery_address = previous_order.delivery_address

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is None:

            messages.error(
                request,
                "Incorrect username or password."
            )

        elif is_tenant_staff(user):

            login(request, user)

            return redirect(
                "staff_dashboard"
            )

        else:

            messages.error(
                request,
                "This account does not have staff access."
            )

    return render(
        request,
        "orders/staff_login.html",
    )

# =========================================================
# MANAGEMENT LOGIN
# =========================================================

def owner_login(request):

    if request.user.is_authenticated:

        if request.user.is_superuser:
            return redirect(
                "owner_dashboard"
            )

        logout(request)

    # =========================================================
    # RETURNING CUSTOMER MEMORY
    # Match by customer name + WhatsApp number and restore
    # the most recent delivery address.
    # =========================================================
    # =========================================================
    # LOGGED-IN CUSTOMER IDENTITY
    # Use the registered CustomerProfile details as the
    # authoritative checkout identity.
    # =========================================================
    if request.user.is_authenticated and hasattr(
        request.user,
        "customer_profile",
    ):
        customer_name = request.user.first_name.strip()
        whatsapp_number = (
            request.user.customer_profile.whatsapp_number.strip()
        )
    if request.method == "GET":
        saved_customer_name = request.session.get(
            "airxpress_customer_name",
            "",
        ).strip()

        saved_whatsapp_number = request.session.get(
            "airxpress_customer_whatsapp",
            "",
        ).strip()

        if saved_customer_name and saved_whatsapp_number:
            previous_order = (
                Order.objects
                .filter(
                    customer_name__iexact=saved_customer_name,
                    whatsapp_number=saved_whatsapp_number,
                    delivery_address__isnull=False,
                )
                .exclude(
                    delivery_address="",
                )
                .order_by("-created_at")
                .first()
            )

            if previous_order:
                customer_name = previous_order.customer_name
                whatsapp_number = previous_order.whatsapp_number
                delivery_address = previous_order.delivery_address

    if request.method == "POST":

        username = request.POST.get(
            "username"
        )

        password = request.POST.get(
            "password"
        )

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is None:

            messages.error(
                request,
                "Incorrect username or password."
            )

        elif user.is_superuser:

            login(
                request,
                user
            )

            return redirect(
                "owner_dashboard"
            )

        else:

            messages.error(
                request,
                "This account does not have management access."
            )

    return render(
        request,
        "orders/owner_login.html",
    )


# =========================================================
# DRIVER DASHBOARD
# =========================================================

@user_passes_test(
    lambda user: (
        user.is_authenticated
        and hasattr(user, "driver_profile")
    ),
    login_url="/driver/login/",
)

@login_required(login_url="/driver/login/")
@user_passes_test(
    lambda user: (
        user.is_authenticated
        and hasattr(user, "driver_profile")
    ),
    login_url="/driver/login/",
)
def driver_update_banking(request):

    driver = request.user.driver_profile

    if request.method != "POST":
        return redirect("driver_dashboard")

    driver.bank_name = request.POST.get(
        "bank_name",
        "",
    ).strip()

    driver.account_holder_name = request.POST.get(
        "account_holder_name",
        "",
    ).strip()

    driver.account_type = request.POST.get(
        "account_type",
        "",
    ).strip()

    driver.branch_code = request.POST.get(
        "branch_code",
        "",
    ).strip()

    

    driver.physical_address = request.POST.get(
        "physical_address",
        "",
    ).strip()
# Existing account numbers are protected.
    # Only replace the number when the driver explicitly
    # selects "Change Account Number".
    change_account_number = (
        request.POST.get(
            "change_account_number",
            "",
        )
        == "1"
    )

    submitted_account_number = request.POST.get(
        "account_number",
        "",
    ).strip()

    if change_account_number:

        if not submitted_account_number:
            messages.error(
                request,
                "Please enter the new account number.",
            )
            return redirect("driver_dashboard")

        driver.account_number = submitted_account_number

    elif not driver.account_number:

        if not submitted_account_number:
            messages.error(
                request,
                "Please enter your account number.",
            )
            return redirect("driver_dashboard")

        driver.account_number = submitted_account_number

    # Any banking change requires verification again.
    driver.banking_status = "pending"

    driver.save()

    messages.success(
        request,
        "Your banking details have been saved and are pending verification.",
    )

    return redirect("driver_dashboard")

def driver_upload_license(request):
    if request.method != "POST":
        return redirect("driver_dashboard")

    driver = request.user.driver_profile

    print("=================================================")
    print("AIRXPRESS LICENSE UPLOAD DEBUG")
    print("REQUEST METHOD:", request.method)
    print("FILES:", list(request.FILES.keys()))
    print("LICENSE FILE:", request.FILES.get("driver_license"))
    print("POST:", dict(request.POST))
    print("=================================================")

    license_file = request.FILES.get("driver_license")

    if not license_file:
        messages.error(
            request,
            "Please select a driver licence file before uploading.",
        )
        return redirect("driver_dashboard")

    driver.driver_license = license_file
    driver.license_verification_status = "pending"
    driver.airxpress_verified = False

    driver.save(
        update_fields=[
            "driver_license",
            "license_verification_status",
            "airxpress_verified",
        ]
    )

    messages.success(
        request,
        "Driver licence uploaded successfully. Your licence is now pending AirXpress verification.",
    )

    return redirect("driver_dashboard")


def driver_update_profile(request):
    if request.method != "POST":
        return redirect("driver_dashboard")

    driver = request.user.driver_profile

    driver.name = request.POST.get("name", "").strip()
    driver.vehicle_make_model = request.POST.get(
        "vehicle_make_model",
        ""
    ).strip()
    driver.vehicle_colour = request.POST.get(
        "vehicle_colour",
        ""
    ).strip()
    driver.vehicle_registration = request.POST.get(
        "vehicle_registration",
        ""
    ).strip()

    if request.FILES.get("driver_license"):
        driver.driver_license = request.FILES["driver_license"]
        driver.license_verification_status = "pending"
        driver.airxpress_verified = False
    if request.FILES.get("photo"):
        driver.photo = request.FILES["photo"]

    driver.save()

    messages.success(
        request,
        "Driver profile updated successfully."
    )

    return redirect("driver_dashboard")

def driver_dashboard(request):

    driver = request.user.driver_profile

    pending_requests = (
        DeliveryRequest.objects
        .filter(
            driver=driver,
            status="pending",
        )
        .select_related(
            "order",
            "order__shop",
        )
        .order_by(
            "-created_at"
        )
    )

    assigned_orders = (
        Order.objects
        .filter(
            driver=driver,
            status__in=[
                "driver_assigned",
                "picked_up",
                "delivered",
            ],
        )
        .select_related(
            "shop",
        )
        .order_by(
            "-updated_at"
        )
    )


    # =========================================================
    # DRIVER PRIVATE EARNINGS
    # =========================================================

    driver_payouts = (
        DriverPayout.objects
        .filter(
            driver=driver,
        )
        .select_related(
            "order",
            "order__shop",
        )
        .order_by(
            "-created_at"
        )
    )

    total_earned = (
        driver_payouts.aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0.00")
    )

    pending_payout = (
        driver_payouts
        .filter(
            status="pending",
        )
        .aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0.00")
    )

    paid_to_date = (
        driver_payouts
        .filter(
            status="paid",
        )
        .aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0.00")
    )

    completed_deliveries = (
        Order.objects
        .filter(
            driver=driver,
            status="collected",
        )
        .count()
    )

    # =========================================================
    # DRIVER DELIVERY HISTORY DATE FILTERS
    # These filters affect history only, not earnings totals.
    # =========================================================

    history_range = request.GET.get("history_range", "all")
    history_start = request.GET.get("history_start", "").strip()
    history_end = request.GET.get("history_end", "").strip()

    history_payouts = driver_payouts

    today = timezone.localdate()

    if history_range == "today":
        history_payouts = history_payouts.filter(
            created_at__date=today
        )

    elif history_range == "7days":
        history_payouts = history_payouts.filter(
            created_at__date__gte=today - timedelta(days=6),
            created_at__date__lte=today,
        )

    elif history_range == "month":
        history_payouts = history_payouts.filter(
            created_at__date__year=today.year,
            created_at__date__month=today.month,
        )

    elif history_range == "custom":
        from django.utils.dateparse import parse_date

        start_date = parse_date(history_start) if history_start else None
        end_date = parse_date(history_end) if history_end else None

        if start_date and end_date and start_date > end_date:
            messages.warning(
                request,
                "The start date must not be after the end date.",
            )
        else:
            if start_date:
                history_payouts = history_payouts.filter(
                    created_at__date__gte=start_date
                )
            if end_date:
                history_payouts = history_payouts.filter(
                    created_at__date__lte=end_date
                )

    # =========================================================
    # DRIVER CUSTOMER RATINGS
    # =========================================================

    reviews = (
        OrderReview.objects
        .filter(
            driver=driver
        )
        .select_related(
            "order",
            "customer",
        )
        .order_by(
            "-created_at"
        )
    )

    driver_review_summary = reviews.aggregate(
        total_reviews=Count("id"),
        average_overall=Avg("overall_rating"),
        average_delivery=Avg("delivery_rating"),
    )

    # Only the most recently updated picked-up order is actively tracked.
    active_delivery = assigned_orders.filter(status="picked_up").first()

    context = {
        "driver": driver,
          "mapbox_token": settings.MAPBOX_TOKEN,
          "active_delivery_id": active_delivery.id if active_delivery else None,
          "active_delivery_latitude": (
              float(active_delivery.customer_latitude)
              if active_delivery and active_delivery.customer_latitude is not None
              else None
          ),
          "active_delivery_longitude": (
              float(active_delivery.customer_longitude)
              if active_delivery and active_delivery.customer_longitude is not None
              else None
          ),
        "pending_requests": pending_requests,
        "assigned_orders": assigned_orders,
        "driver_payouts": driver_payouts,
        "history_payouts": history_payouts,
        "history_range": history_range,
        "history_start": history_start,
        "history_end": history_end,
        "total_earned": total_earned,
        "pending_payout": pending_payout,
        "paid_to_date": paid_to_date,
        "completed_deliveries": completed_deliveries,
        "reviews": reviews,
        "total_driver_reviews": driver_review_summary["total_reviews"] or 0,
        "average_driver_rating": driver_review_summary["average_overall"],
        "average_delivery_rating": driver_review_summary["average_delivery"],
    }

    return render(
        request,
        "orders/driver_dashboard.html",
        context,
    )


# =========================================================
# DRIVER ACCEPT DELIVERY REQUEST
# =========================================================

@user_passes_test(
    lambda user: (
        user.is_authenticated
        and hasattr(user, "driver_profile")
    ),
    login_url="/driver/login/",
)
def driver_accept_request(
    request,
    request_id,
):

    if request.method != "POST":
        return redirect("driver_dashboard")

    driver = request.user.driver_profile

    if (
        not driver.airxpress_verified
        or driver.license_verification_status != "verified"
    ):
        messages.warning(
            request,
            "Your AirXpress driver profile is not yet verified. Please upload your driver licence and wait for AirXpress verification.",
        )
        return redirect("driver_dashboard")


    with transaction.atomic():

        driver = Driver.objects.select_for_update().get(
            pk=driver.pk
        )

        if not driver.is_available:
            messages.warning(
                request,
                "You are currently unavailable for deliveries. Complete your active delivery before accepting another request.",
            )
            return redirect("driver_dashboard")

        has_active_order = Order.objects.filter(
            driver=driver,
            status__in=[
                "driver_assigned",
                "picked_up",
                "delivered",
            ],
        ).exists()

        if has_active_order:
            messages.warning(
                request,
                "You already have an active delivery. Complete it before accepting another request.",
            )
            return redirect("driver_dashboard")

        delivery_request = get_object_or_404(
            DeliveryRequest.objects.select_for_update(),
            id=request_id,
            driver=driver,
            status="pending",
        )

        order = (
            Order.objects
            .select_for_update()
            .get(
                id=delivery_request.order_id
            )
        )

        # Payment must be confirmed before driver acceptance.
        if order.payment_status != "paid":
            messages.warning(
                request,
                "This order cannot be accepted because payment has not been confirmed."
            )
            return redirect("driver_dashboard")

        # Another driver may have accepted first.
        if order.driver_id:

            delivery_request.status = "declined"
            delivery_request.responded_at = timezone.now()
            delivery_request.save(
                update_fields=[
                    "status",
                    "responded_at",
                ]
            )

            messages.warning(
                request,
                (
                    f"Order #{order.id} has already "
                    "been assigned to another driver."
                )
            )

            return redirect("driver_dashboard")

        # The order must still be ready for delivery.
        if order.status != "ready":

            delivery_request.status = "declined"
            delivery_request.responded_at = timezone.now()
            delivery_request.save(
                update_fields=[
                    "status",
                    "responded_at",
                ]
            )

            messages.warning(
                request,
                (
                    f"Order #{order.id} is no longer "
                    "available for delivery."
                )
            )

            return redirect("driver_dashboard")

        # Assign this driver.
        order.driver = driver
        order.status = "driver_assigned"
        order.save(
            update_fields=[
                "driver",
                "status",
                "updated_at",
            ]
        )

        # Accept this request.
        delivery_request.status = "accepted"
        delivery_request.responded_at = timezone.now()
        delivery_request.save(
            update_fields=[
                "status",
                "responded_at",
            ]
        )

        # Make the driver unavailable while handling this delivery.
        driver.is_available = False
        driver.save(
            update_fields=[
                "is_available",
            ]
        )

        # Close all other pending requests for this order.
        DeliveryRequest.objects.filter(
            order=order,
            status="pending",
        ).exclude(
            id=delivery_request.id,
        ).update(
            status="expired",
            responded_at=timezone.now(),
        )

        OrderStatusHistory.objects.create(
            order=order,
            status="driver_assigned",
            notes=(
                f"Driver {driver.name} accepted "
                f"the delivery request."
            ),
        )

    messages.success(
        request,
        (
            f"Order #{order.id} has been assigned to you."
        )
    )

    return redirect("driver_dashboard")


# =========================================================
# DRIVER DECLINE DELIVERY REQUEST
# =========================================================

@user_passes_test(
    lambda user: (
        user.is_authenticated
        and hasattr(user, "driver_profile")
    ),
    login_url="/driver/login/",
)
def driver_decline_request(
    request,
    request_id,
):

    if request.method != "POST":
        return redirect("driver_dashboard")

    driver = request.user.driver_profile

    delivery_request = get_object_or_404(
        DeliveryRequest,
        id=request_id,
        driver=driver,
        status="pending",
    )

    delivery_request.status = "declined"
    delivery_request.responded_at = timezone.now()

    delivery_request.save(
        update_fields=[
            "status",
            "responded_at",
        ]
    )

    messages.info(
        request,
        (
            f"Delivery request for Order "
            f"#{delivery_request.order_id} declined."
        )
    )

    return redirect("driver_dashboard")


# =========================================================
# DRIVER PICK UP ORDER
# =========================================================

@user_passes_test(
    lambda user: (
        user.is_authenticated
        and hasattr(user, "driver_profile")
    ),
    login_url="/driver/login/",
)
def driver_pickup_order(request, order_id):

    if request.method != "POST":
        return redirect("driver_dashboard")

    driver = request.user.driver_profile

    with transaction.atomic():

        order = get_object_or_404(
            Order.objects.select_for_update().select_related(
                "driver",
                "shop",
            ),
            id=order_id,
            driver=driver,
        )

        if order.status != "driver_assigned":
            messages.warning(
                request,
                (
                    f"Order #{order.id} is not ready "
                    "to be picked up."
                )
            )
            return redirect("driver_dashboard")

        if (
            order.shop is None
            or order.shop.latitude is None
            or order.shop.longitude is None
        ):
            messages.error(
                request,
                (
                    "Pickup cannot be completed because "
                    "the shop does not have GPS coordinates."
                )
            )
            return redirect("driver_dashboard")

        if (
            order.driver_latitude is None
            or order.driver_longitude is None
        ):
            messages.error(
                request,
                (
                    "AirXpress GPS location has not been "
                    "received yet. Please enable GPS and "
                    "wait for your location to update."
                )
            )
            return redirect("driver_dashboard")

        if order.driver_location_updated_at is None:
            messages.error(
                request,
                (
                    "AirXpress has not received a current "
                    "GPS location. Please wait for GPS "
                    "to update."
                )
            )
            return redirect("driver_dashboard")

        gps_age_seconds = (
            timezone.now()
            - order.driver_location_updated_at
        ).total_seconds()

        if gps_age_seconds > 120:
            messages.error(
                request,
                (
                    "Your AirXpress GPS location is too old. "
                    "Please wait for your live location to "
                    "update before picking up the order."
                )
            )
            return redirect("driver_dashboard")

        pickup_distance_km = calculate_distance_km(
            order.driver_latitude,
            order.driver_longitude,
            order.shop.latitude,
            order.shop.longitude,
        )

        pickup_distance_metres = (
            pickup_distance_km * 1000
        )

        PICKUP_RADIUS_METRES = 250

        if pickup_distance_metres > PICKUP_RADIUS_METRES:
            messages.warning(
                request,
                (
                    f"You are still "
                    f"{pickup_distance_metres:.0f} metres "
                    "from the pickup shop. You must be "
                    "within 250 metres of the shop before "
                    "you can pick up this order."
                )
            )
            return redirect("driver_dashboard")

        order.status = "picked_up"

        order.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        OrderStatusHistory.objects.create(
            order=order,
            status="picked_up",
            notes=(
                f"Driver {driver.name} picked up "
                f"Order #{order.id} at the shop. "
                f"AirXpress GPS distance was "
                f"{pickup_distance_metres:.0f} metres."
            ),
        )

    messages.success(
        request,
        (
            f"Order #{order.id} has been picked up. "
            "AirXpress live GPS tracking is now active "
            "for the delivery."
        )
    )

    return redirect("driver_dashboard")


@user_passes_test(
    lambda user: (
        user.is_authenticated
        and hasattr(user, "driver_profile")
    ),
    login_url="/driver/login/",
)
def driver_deliver_order(request, order_id):

    if request.method != "POST":
        return redirect("driver_dashboard")

    driver = request.user.driver_profile

    with transaction.atomic():

        order = get_object_or_404(
            Order.objects.select_for_update(),
            id=order_id,
            driver=driver,
        )

        if order.status != "picked_up":
            messages.warning(
                request,
                f"Order #{order.id} cannot be marked as delivered yet."
            )
            return redirect("driver_dashboard")

        order.status = "delivered"

        # Stop live GPS tracking when delivery is completed.
        order.driver_latitude = None
        order.driver_longitude = None
        order.driver_location_updated_at = None

        order.save(
            update_fields=[
                "status",
                "driver_latitude",
                "driver_longitude",
                "driver_location_updated_at",
                "updated_at",
            ]
        )

        OrderStatusHistory.objects.create(
            order=order,
            status="delivered",
            notes=(
                f"Driver {driver.name} marked "
                f"Order #{order.id} as delivered."
            ),
        )

    messages.success(
        request,
        f"Order #{order.id} has been marked as delivered."
    )

    return redirect("driver_dashboard")


# =========================================================
# DRIVER COMPLETE DELIVERY
# =========================================================

@user_passes_test(
    lambda user: (
        user.is_authenticated
        and hasattr(user, "driver_profile")
    ),
    login_url="/driver/login/",
)
def driver_complete_delivery(request, order_id):

    if request.method != "POST":
        return redirect("driver_dashboard")

    driver = request.user.driver_profile

    with transaction.atomic():

        order = get_object_or_404(
            Order.objects.select_for_update(),
            id=order_id,
            driver=driver,
        )

        if order.status != "delivered":
            messages.warning(
                request,
                f"Order #{order.id} must be delivered before it can be completed."
            )
            return redirect("driver_dashboard")

        if order.delivery_qr_verified_at is None:
            messages.warning(
                request,
                f"Scan the customer's QR code before completing Order #{order.id}."
            )
            return redirect("driver_dashboard")

        order.status = "collected"

        order.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        # =============================================
        # DRIVER PAYOUT
        # =============================================

        DriverPayout.objects.get_or_create(
            order=order,
            defaults={
                "driver": driver,
                "amount": order.driver_payout,
                "status": "pending",
            },
        )

        # Driver is available for another delivery.
        driver.is_available = True

        driver.save(
            update_fields=[
                "is_available",
            ]
        )

        OrderStatusHistory.objects.create(
            order=order,
            status="collected",
            notes=(
                f"Driver {driver.name} completed "
                f"Order #{order.id} and is available again."
            ),
        )

    messages.success(
        request,
        (
            f"Order #{order.id} has been completed. "
            "You are now available for another delivery."
        )
    )

    return redirect("driver_dashboard")


# =========================================================
# STAFF DASHBOARD
# =========================================================





# =========================================================
# CUSTOMER DELIVERY QR VERIFICATION
# =========================================================

@user_passes_test(
    lambda user: user.is_authenticated and hasattr(user, "driver_profile"),
    login_url="/driver/login/",
)
def driver_scan_delivery_qr(request, order_id):
    driver = request.user.driver_profile
    order = get_object_or_404(Order, id=order_id, driver=driver)

    if order.status != "delivered":
        messages.warning(request, "Mark this order as delivered before scanning its QR.")
        return redirect("driver_dashboard")

    if order.delivery_qr_verified_at is not None:
        messages.warning(request, "This QR code has already been used.")
        return redirect("driver_dashboard")

    return render(request, "orders/driver_qr_scan.html", {"order": order})


@user_passes_test(
    lambda user: user.is_authenticated and hasattr(user, "driver_profile"),
    login_url="/driver/login/",
)
def driver_verify_delivery_qr(request, order_id):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "POST is required."}, status=405)

    driver = request.user.driver_profile
    try:
        token = uuid.UUID((request.POST.get("token") or "").strip())
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"success": False, "message": "Invalid QR code."}, status=400)

    with transaction.atomic():
        order = (
            Order.objects.select_for_update()
            .filter(id=order_id, driver=driver, delivery_qr_token=token)
            .first()
        )

        if order is None:
            return JsonResponse({
                "success": False,
                "message": "This QR does not belong to your assigned order.",
            }, status=403)

        if order.status != "delivered":
            return JsonResponse({
                "success": False,
                "message": "The order must be marked delivered first.",
            }, status=409)

        if order.delivery_qr_verified_at is not None:
            return JsonResponse({
                "success": False,
                "message": "This QR code has already been used.",
            }, status=409)

        order.delivery_qr_verified_at = timezone.now()
        order.status = "collected"
        order.save(update_fields=["delivery_qr_verified_at", "status", "updated_at"])

        DriverPayout.objects.get_or_create(
            order=order,
            defaults={
                "driver": driver,
                "amount": order.driver_payout,
                "status": "pending",
            },
        )

        driver.is_available = True
        driver.save(update_fields=["is_available"])

        OrderStatusHistory.objects.create(
            order=order,
            status="collected",
            notes=(
                f"Driver {driver.name} completed Order #{order.id} "
                "after customer QR verification."
            ),
        )

    return JsonResponse({
        "success": True,
        "message": f"Order #{order.id} verified and completed.",
        "redirect_url": reverse("driver_dashboard"),
    })


@user_passes_test(
    is_tenant_staff,
    login_url="/staff/login/"
)
def staff_dashboard(request):

    shop = get_user_shop(request.user)

    if not shop:
        return render(
            request,
            "orders/no_shop.html",
        )

    orders = (
        Order.objects
        .filter(
            shop=shop
        )
        .exclude(
            status__in=[
                "delivered",
                "collected",
                "cancelled",
            ]
        )
        .prefetch_related(
            "items__menu_item",
        )
        .order_by(
            "-created_at"
        )
    )

    drivers = (
        Driver.objects
        .filter(
            is_available=True,
            airxpress_verified=True,
            license_verification_status="verified",
        )
        .order_by("name")
    )

    # SHOP DASHBOARD STATUS COUNTS
    # =========================================================

    new_orders = orders.filter(
        status="new"
    ).count()

    preparing_orders = orders.filter(
        status="preparing"
    ).count()
    ready_orders = orders.filter(
        status="ready"
    ).count()

    driver_assigned_orders = orders.filter(
        status="driver_assigned"
    ).count()

    picked_up_orders = orders.filter(
        status="picked_up"
    ).count()

    on_the_way_orders = orders.filter(
        status="on_the_way"
    ).count()

    # =========================================================
    # =========================================================
    # CUSTOMER REVIEWS
    # =========================================================

    reviews = (
        OrderReview.objects
        .filter(
            shop=shop
        )
        .select_related(
            "order",
            "customer",
            "driver",
        )
        .order_by(
            "-created_at"
        )
    )

    review_summary = reviews.aggregate(
        total_reviews=Count("id"),
        average_overall=Avg("overall_rating"),
        average_food=Avg("food_rating"),
        average_delivery=Avg("delivery_rating"),
    )
    # DASHBOARD CONTEXT
    # =========================================================

    context = {
        "shop": shop,
        "orders": orders,
        "drivers": drivers,

        "new_orders": new_orders,
        "preparing_orders": preparing_orders,
        "ready_orders": ready_orders,
        "driver_assigned_orders": driver_assigned_orders,
        "picked_up_orders": picked_up_orders,
        "on_the_way_orders": on_the_way_orders,

        "reviews": reviews,
        "total_reviews": review_summary["total_reviews"] or 0,
        "average_overall_rating": review_summary["average_overall"],
        "average_food_rating": review_summary["average_food"],
        "average_delivery_rating": review_summary["average_delivery"],
    }

    return render(
        request,
        "orders/staff_dashboard.html",
        context,
    )




# =========================================================
# SHOP BANKING DETAILS
# =========================================================

@login_required(login_url="/staff/login/")
def shop_banking_details(request):
    profile = get_staff_profile(request.user)

    if profile is None:
        messages.error(request, "You are not authorised to access shop banking details.")
        return redirect("staff_login")

    shop = profile.shop

    if request.method == "POST":
        bank_name = request.POST.get("bank_name", "").strip()
        account_holder_name = request.POST.get("account_holder_name", "").strip()
        account_number = request.POST.get("account_number", "").strip()
        account_type = request.POST.get("account_type", "").strip()
        branch_code = request.POST.get("branch_code", "").strip()

        if not all([
            bank_name,
            account_holder_name,
            account_number,
            account_type,
            branch_code,
        ]):
            messages.error(request, "Please complete all banking fields.")
        else:
            changed = any([
                shop.bank_name != bank_name,
                shop.account_holder_name != account_holder_name,
                shop.account_number != account_number,
                shop.account_type != account_type,
                shop.branch_code != branch_code,
            ])

            shop.bank_name = bank_name
            shop.account_holder_name = account_holder_name
            shop.account_number = account_number
            shop.account_type = account_type
            shop.branch_code = branch_code

            if changed:
                shop.banking_status = "pending"

            shop.save()
            messages.success(
                request,
                "Shop banking details saved. Verification status: "
                + shop.get_banking_status_display() + ".",
            )
            return redirect("shop_banking_details")

    return render(
        request,
        "orders/shop_banking_details.html",
        {"shop": shop},
    )

# =========================================================
# AUTOMATIC DRIVER DISPATCH HELPER
# =========================================================

def dispatch_order_to_available_drivers(order):

    # Payment must be confirmed before dispatch.
    if order.payment_status != "paid":
        return 0

    # Do not dispatch an order that already has a driver.
    if order.driver_id:
        return 0

    # Only delivery orders require a driver.
    if order.order_type != "delivery":
        return 0

    available_drivers = (
        Driver.objects.filter(is_available=True, airxpress_verified=True, license_verification_status="verified")
        .order_by(
            "name"
        )
    )

    created_count = 0

    for driver in available_drivers:

        existing_request = (
            DeliveryRequest.objects
            .filter(
                order=order,
                driver=driver,
                status="pending",
            )
            .exists()
        )

        if existing_request:
            continue

        delivery_request = DeliveryRequest.objects.create(
            order=order,
            driver=driver,
            status="pending",
        )

        # Notify the driver only after the request is committed.
        def send_push_safely(driver_id, request_id):
            try:
                from .push_notifications import send_driver_push_notification
                send_driver_push_notification(driver_id, request_id)
            except Exception:
                # Push failures must never interrupt order dispatch.
                import logging
                logging.getLogger(__name__).exception(
                    "Driver push notification failed for request %s.",
                    request_id,
                )

        transaction.on_commit(
            lambda driver_id=driver.pk, request_id=delivery_request.pk:
                send_push_safely(driver_id, request_id)
        )

        created_count += 1

    return created_count


# =========================================================
@user_passes_test(
    is_tenant_staff,
    login_url="/staff/login/"
)


# STAFF NOTIFY NEARBY DRIVERS

@user_passes_test(
    is_tenant_staff,
    login_url="/staff/login/"
)
def staff_notify_drivers(request, order_id):

    if request.method != "POST":
        return redirect("staff_dashboard")

    shop = get_user_shop(request.user)

    if not shop:
        return redirect("staff_login")

    order = get_object_or_404(
        Order,
        id=order_id,
        shop=shop,
    )

    if order.order_type != "delivery":
        messages.error(
            request,
            f"Order #{order.id} is not a delivery order."
        )
        return redirect("staff_dashboard")

    if order.status != "ready":
        messages.error(
            request,
            f"Order #{order.id} must be Ready before drivers can be notified."
        )
        return redirect("staff_dashboard")

    if order.driver_id:
        messages.info(
            request,
            f"Order #{order.id} already has a driver assigned."
        )
        return redirect("staff_dashboard")

    requests_created = dispatch_order_to_available_drivers(order)

    if requests_created > 0:
        messages.success(
            request,
            (
                f"Order #{order.id}: delivery request sent to "
                f"{requests_created} available driver(s)."
            )
        )
    elif order.payment_status != "paid":
        messages.warning(
            request,
            (
                f"Order #{order.id} cannot be dispatched because "
                "payment has not yet been confirmed."
            )
        )
    else:
        messages.warning(
            request,
            f"Order #{order.id}: no available drivers were found."
        )

    return redirect("staff_dashboard")


# STAFF UPDATE ORDER
# =========================================================

@user_passes_test(
    is_tenant_staff,
    login_url="/staff/login/"
)
def staff_update_order(
    request,
    order_id,
):

    shop = get_user_shop(request.user)

    if not shop:
        return redirect("staff_login")

    order = get_object_or_404(
        Order,
        id=order_id,
        shop=shop,
    )

    # =========================================================
    # RETURNING CUSTOMER MEMORY
    # Match by customer name + WhatsApp number and restore
    # the most recent delivery address.
    # =========================================================
    # =========================================================
    # LOGGED-IN CUSTOMER IDENTITY
    # Use the registered CustomerProfile details as the
    # authoritative checkout identity.
    # =========================================================
    if request.user.is_authenticated and hasattr(
        request.user,
        "customer_profile",
    ):
        customer_name = request.user.first_name.strip()
        whatsapp_number = (
            request.user.customer_profile.whatsapp_number.strip()
        )
    if request.method == "GET":
        saved_customer_name = request.session.get(
            "airxpress_customer_name",
            "",
        ).strip()

        saved_whatsapp_number = request.session.get(
            "airxpress_customer_whatsapp",
            "",
        ).strip()

        if saved_customer_name and saved_whatsapp_number:
            previous_order = (
                Order.objects
                .filter(
                    customer_name__iexact=saved_customer_name,
                    whatsapp_number=saved_whatsapp_number,
                    delivery_address__isnull=False,
                )
                .exclude(
                    delivery_address="",
                )
                .order_by("-created_at")
                .first()
            )

            if previous_order:
                customer_name = previous_order.customer_name
                whatsapp_number = previous_order.whatsapp_number
                delivery_address = previous_order.delivery_address

    if request.method == "POST":# =============================================
        # STATUS
        # =============================================

        # =============================================
        # STATUS - ENFORCED
        # =============================================

        status = request.POST.get("status")

        previous_status = order.status

        valid_statuses = dict(Order.STATUS_CHOICES)

        if not status:
            messages.error(
                request,
                "Please select an order status."
            )
            return redirect("staff_dashboard")

        if status not in valid_statuses:
            messages.error(
                request,
                "Invalid order status."
            )
            return redirect("staff_dashboard")

        order.status = status
        # =============================================
        # =============================================
        # DELIVERY PRICE LOCK
        # =============================================

        if order.status == "picked_up":

            if order.order_type != "delivery":
                messages.error(
                    request,
                    "Only delivery orders can be picked up for delivery."
                )
                return redirect("staff_dashboard")

            # Delivery distance and pricing are confirmed at checkout.
            # Never recalculate the customer's price at pickup.

            if order.delivery_distance_km <= 0:
                messages.error(
                    request,
                    "Delivery pricing has not been confirmed at checkout."
                )
                return redirect("staff_dashboard")

            if order.delivery_fee <= 0:
                messages.error(
                    request,
                    "The delivery fee has not been confirmed at checkout."
                )
                return redirect("staff_dashboard")

            if not order.final_total:
                messages.error(
                    request,
                    "The customer's final total has not been confirmed at checkout."
                )
                return redirect("staff_dashboard")
        # DRIVER
        # =============================================
        # =============================================
        # PAYMENT STATUS
        # =============================================

        # =============================================
        # PAYMENT STATUS - SYSTEM CONTROLLED
        # =============================================
        # Staff cannot manually change payment status.
        # PayFast / legitimate payment flows control this.
        # =============================================

        payment_status = order.payment_status

        # =============================================
        # DRIVER ASSIGNMENT - SYSTEM CONTROLLED
        # =============================================
        # Staff cannot manually assign a driver.
        # Driver assignment happens when a driver accepts
        # an automatically created delivery request.
        # =============================================

        if order.status in [
            "driver_assigned",
            "picked_up",
            "on_the_way",
        ] and not order.driver_id:

            messages.error(
                request,
                "A delivery driver must be assigned before this order can continue."
            )

            return redirect("staff_dashboard")
        # SAVE ORDER
        # =============================================

        order.save()

        # =============================================
        # STATUS HISTORY
        # =============================================

        OrderStatusHistory.objects.create(
            order=order,
            status=order.status,
            notes="Order updated by staff.",
        )

        # =============================================
        # AUTOMATIC DRIVER DISPATCH
        # =============================================

        if (
            order.status == "ready"
            and previous_status != "ready"
            and not order.driver_id
        ):

            requests_created = (
                dispatch_order_to_available_drivers(
                    order
                )
            )

            if requests_created > 0:

                messages.success(
                    request,
                    (
                        f"Order #{order.id} is ready. "
                        f"Delivery request sent to "
                        f"{requests_created} available driver(s)."
                    )
                )

            elif order.payment_status != "paid":

                messages.warning(
                    request,
                    (
                        f"Order #{order.id} is ready, "
                        "but payment has not yet been confirmed. "
                        "Driver dispatch will occur after payment is confirmed."
                    )
                )

            else:

                messages.warning(
                    request,
                    (
                        f"Order #{order.id} is ready, "
                        "but no available drivers were found."
                    )
                )

    return redirect(
        "staff_dashboard"
    )


# =========================================================
# STAFF ORDER HISTORY
# =========================================================

@user_passes_test(
    is_tenant_staff,
    login_url="/staff/login/"
)
def staff_order_history(request):

    shop = get_user_shop(request.user)


    if not shop:
        return render(
            request,
            "orders/no_shop.html",
        )

    orders = (
        Order.objects
        .filter(
            shop=shop,
            status__in=[
                "collected",
                "cancelled",
            ]
        )
        .prefetch_related(
            "items__menu_item",
        )
        .order_by(
            "-updated_at"
        )
    )

    return render(
        request,
        "orders/staff_order_history.html",
        {
            "shop": shop,
            "orders": orders,
        },
    )

# =========================================================
# STAFF DAILY MANAGER REPORT
# =========================================================

@user_passes_test(
    is_tenant_staff,
    login_url="/staff/login/"
)
def staff_daily_report(request):

    shop = get_user_shop(request.user)


    if not shop:
        return render(
            request,
            "orders/no_shop.html",
        )

    # =====================================================
    # REPORT DATE
    # =====================================================

    from django.utils import timezone
    from datetime import datetime
    from django.db.models import Sum
# Imports already defined at the top of this file.
    from django.db.models.functions import Coalesce

    selected_date_string = request.GET.get(
        "date"
    )

    if selected_date_string:

        try:
            selected_date = datetime.strptime(
                selected_date_string,
                "%Y-%m-%d"
            ).date()

        except ValueError:
            selected_date = timezone.localdate()

    else:
        selected_date = timezone.localdate()

    # =====================================================
    # ORDERS FOR SELECTED DAY
    # =====================================================

    orders = (
        Order.objects
        .filter(
            shop=shop,
            created_at__date=selected_date,
        )
        .prefetch_related(
            "items__menu_item",
        )
        .order_by(
            "-created_at"
        )
    )

    # =====================================================
    # ORDER COUNTS
    # =====================================================

    total_orders = orders.count()

    collected_orders = orders.filter(
        status="collected"
    ).count()

    cancelled_orders = orders.filter(
        status="cancelled"
    ).count()

    new_orders = orders.filter(
        status="new"
    ).count()

    preparing_orders = orders.filter(
        status="preparing"
    ).count()
    ready_orders = orders.filter(
        status="ready"
    ).count()

    in_progress_orders = orders.filter(
        status__in=[
            "new",
            "preparing",
            "braaiing",
            "ready",
        ]
    ).count()

    # =====================================================
    # ORDER SOURCES
    # =====================================================

    online_orders = orders.filter(
        order_source="online"
    ).count()
# =====================================================
    # ORDER TYPES
    # =====================================================

    # =====================================================
    # PAYMENT COUNTS
    # =====================================================

    paid_orders = orders.filter(
        payment_status="paid"
    ).count()

    pending_payment_orders = orders.filter(
        payment_status="pending"
    ).count()

    # =====================================================
    # SALES
    #
    # Cancelled orders are excluded.
    # final_total is preferred.
    # estimated_total is used when final_total is empty.
    # =====================================================

    valid_orders = orders.exclude(
        status="cancelled"
    )

    total_sales = Decimal("0.00")
    paid_sales = Decimal("0.00")
    outstanding_sales = Decimal("0.00")

    for order in valid_orders:

        amount = (
            order.final_total
            if order.final_total is not None
            else order.estimated_total
        )

        amount = amount or Decimal("0.00")

        total_sales += amount

        if order.payment_status == "paid":
            paid_sales += amount
        else:
            outstanding_sales += amount

    if valid_orders.count() > 0:

        average_order_value = (
            total_sales
            / Decimal(valid_orders.count())
        )

    else:

        average_order_value = Decimal("0.00")

    # =====================================================
    # TOP MENU ITEMS
    # =====================================================

    order_items = (
        OrderItem.objects
        .filter(
            order__shop=shop,
            order__created_at__date=selected_date,
        )
        .exclude(
            order__status="cancelled"
        )
        .select_related(
            "menu_item"
        )
    )

    item_report = {}

    for item in order_items:

        item_name = item.menu_item.name

        if item_name not in item_report:

            item_report[item_name] = {
                "name": item_name,
                "pricing_type": (
                    item.menu_item.pricing_type
                ),
                "quantity": 0,
                "order_count": 0,
                "value": Decimal("0.00"),
            }

        item_report[item_name][
            "order_count"
        ] += 1

        # Fixed-price products
        if (
            item.menu_item.pricing_type
            == "fixed"
        ):

            item_report[item_name][
                "quantity"
            ] += item.quantity

            if item.shop_amount is not None:

                item_value = item.shop_amount

            elif item.final_amount is not None:

                item_value = item.final_amount

            elif item.unit_price is not None:

                item_value = (
                    item.unit_price
                    * item.quantity
                )

            else:

                item_value = (
                    item.requested_amount
                )

        # Amount-based products such as meat
        else:

            if item.final_amount is not None:

                item_value = item.final_amount

            elif item.shop_amount is not None:

                item_value = item.shop_amount

            else:

                item_value = item.requested_amount

        item_report[item_name][
            "value"
        ] += (
            item_value
            or Decimal("0.00")
        )

    top_items = sorted(
        item_report.values(),
        key=lambda item: (
            item["value"],
            item["order_count"],
        ),
        reverse=True,
    )

    # =====================================================
    # DRIVER ACTIVITY
    # =====================================================

    driver_report = (
        orders
        .exclude(
            driver__isnull=True
        )
        .values(
            "driver__name"
        )
        .annotate(
            order_count=Count("id")
        )
        .order_by(
            "-order_count"
        )
    )

    # =====================================================
    # CONTEXT
    # =====================================================


    # =========================================================
    context = {
        "shop": shop,
        "selected_date": selected_date,

        # Orders
        "orders": orders,
        "total_orders": total_orders,
        "collected_orders": collected_orders,
        "cancelled_orders": cancelled_orders,
        "in_progress_orders": in_progress_orders,

        # Individual statuses
        "new_orders": new_orders,
        "preparing_orders": preparing_orders,
        "ready_orders": ready_orders,

        # Sales
        "total_sales": total_sales,
        "paid_sales": paid_sales,
        "outstanding_sales": outstanding_sales,
        "average_order_value": average_order_value,

        # Items
        "top_items": top_items,

        # Drivers
        "driver_report": driver_report,
    }
    return render(
        request,
        "orders/staff_daily_report.html",
        context,
    )


# =========================================================
# AIRXPRESS EATS OWNER DASHBOARD
# =========================================================

@user_passes_test(
    is_owner,
    login_url="/owner/login/"
)

# =========================================================
# DRIVER PAYOUT MANAGEMENT
# =========================================================

@user_passes_test(
    is_owner,
    login_url="/owner/login/"
)
def owner_driver_payouts(request):

    payouts = (
        DriverPayout.objects
        .select_related(
            "driver",
            "order",
            "order__shop",
        )
        .order_by(
            "status",
            "-created_at",
        )
    )

    pending_payouts = payouts.filter(
        status="pending",
    )

    paid_payouts = payouts.filter(
        status="paid",
    )

    pending_total = (
        pending_payouts.aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0.00")
    )

    paid_total = (
        paid_payouts.aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0.00")
    )

    from datetime import timedelta

    today = timezone.localdate()
    default_week_start = today - timedelta(days=today.weekday())

    weekly_batches = (
        DriverPayoutBatch.objects
        .select_related("driver")
        .prefetch_related("payouts__order__shop")
        .order_by("-week_start", "driver__name")
    )

    # =========================================================
    context = {
        "weekly_batches": weekly_batches,
        "default_week_start": default_week_start.isoformat(),
        "payouts": payouts,
        "pending_payouts": pending_payouts,
        "paid_payouts": paid_payouts,
        "pending_total": pending_total,
        "paid_total": paid_total,
    }

    return render(
        request,
        "orders/owner_driver_payouts.html",
        context,
    )


@user_passes_test(
    is_owner,
    login_url="/owner/login/"
)

@user_passes_test(
    is_owner,
    login_url="/owner/login/"
)
def download_driver_payout_statement(request, payout_id):
    payout = get_object_or_404(
        DriverPayout.objects.select_related(
            "driver",
            "order",
            "order__shop",
        ),
        id=payout_id,
    )

    if payout.status != "paid":
        messages.error(
            request,
            "A statement is available only after the payout is recorded as paid.",
        )
        return redirect("owner_driver_payouts")

    if not payout.statement_number:
        payout.statement_number = f"AXD-{payout.id:06d}"
        payout.save(update_fields=["statement_number", "updated_at"])

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=45,
        leftMargin=45,
        topMargin=45,
        bottomMargin=45,
    )

    styles = getSampleStyleSheet()
    story = [
        Paragraph("AIRXPRESS EATS", styles["Title"]),
        Paragraph("Driver Payment Statement", styles["Heading2"]),
        Spacer(1, 12),
    ]

    paid_date = (
        payout.paid_at.strftime("%d %B %Y at %H:%M")
        if payout.paid_at
        else "-"
    )

    statement_data = [
        ["Statement Number", payout.statement_number],
        ["Driver", str(payout.driver.name)],
        ["Order Number", f"#{payout.order.id}"],
        ["Shop", str(payout.order.shop.name)],
        ["Payment Status", "Paid"],
        ["Amount Paid", f"R {payout.amount:,.2f}"],
        ["Payment Date", paid_date],
        ["Bank Transaction Reference", payout.payment_reference or "-"],
        ["Payment Notes", payout.payment_notes or "-"],
    ]

    table = Table(statement_data, colWidths=[180, 320])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EAF0F6")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#172B4D")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))

    story.extend([
        table,
        Spacer(1, 18),
        Paragraph(
            "This statement records the payment details entered in AirXpress Eats. "
            "It is not a bank-issued proof of transfer.",
            styles["Normal"],
        ),
    ])

    document.build(story)
    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="driver-payment-{payout.statement_number}.pdf"'
    )
    return response
@user_passes_test(
    is_owner,
    login_url="/owner/login/"
)
def mark_driver_payout_paid(request, payout_id):
    if request.method != "POST":
        return redirect("owner_driver_payouts")

    payment_reference = request.POST.get("payment_reference", "").strip()
    payment_notes = request.POST.get("payment_notes", "").strip()

    if not payment_reference:
        messages.error(
            request,
            "Enter the bank transaction reference before confirming payment.",
        )
        return redirect("owner_driver_payouts")

    with transaction.atomic():
        payout = get_object_or_404(
            DriverPayout.objects.select_for_update(),
            id=payout_id,
        )

        if payout.status == "paid":
            messages.info(
                request,
                f"Payout for Order #{payout.order.id} has already been marked as paid.",
            )
            return redirect("owner_driver_payouts")

        if payout.batch_id and payout.batch.status == "pending":
            messages.error(
                request,
                f"Payout for Order #{payout.order.id} belongs to weekly batch "
                f"{payout.batch.statement_number}. Process payment through the batch "
                "to keep the weekly statement and individual records consistent.",
            )
            return redirect("owner_driver_payouts")

        if not payout.driver.bank_name or not payout.driver.account_number:
            messages.error(
                request,
                "This driver's bank details are incomplete. Payment was not marked as paid.",
            )
            return redirect("owner_driver_payouts")

        if payout.driver.banking_status != "verified":
            messages.error(
                request,
                "This driver's bank details must be verified before payment can be confirmed.",
            )
            return redirect("owner_driver_payouts")

        payout.payment_reference = payment_reference
        payout.payment_notes = payment_notes
        payout.status = "paid"
        payout.paid_at = timezone.now()

        payout.save(
            update_fields=[
                "payment_reference",
                "payment_notes",
                "status",
                "paid_at",
                "updated_at",
            ]
        )

    messages.success(
        request,
        f"Driver payout for Order #{payout.order.id} recorded as paid. Reference: {payment_reference}",
    )
    return redirect("owner_driver_payouts")

@user_passes_test(
    is_owner,
    login_url="/owner/login/"
)
def create_weekly_driver_payout_batches(request):
    if request.method != "POST":
        return redirect("owner_driver_payouts")

    from datetime import date, timedelta

    raw_week_start = request.POST.get("week_start", "").strip()

    try:
        week_start = date.fromisoformat(raw_week_start)
    except (ValueError, TypeError):
        messages.error(request, "Choose a valid Monday for the payout week.")
        return redirect("owner_driver_payouts")

    if week_start.weekday() != 0:
        messages.error(request, "The payout week must start on a Monday.")
        return redirect("owner_driver_payouts")

    week_end = week_start + timedelta(days=6)
    created_count = 0
    assigned_count = 0
    skipped_count = 0

    with transaction.atomic():
        eligible_payouts = list(
            DriverPayout.objects.select_for_update()
            .select_related("driver", "order", "order__shop")
            .filter(
                status="pending",
                batch__isnull=True,
                order__status__in=["delivered", "collected"],
                order__payment_status="paid",
            )
            .order_by("driver_id", "id")
        )

        grouped = {}
        for payout in eligible_payouts:
            latest_history = payout.order.status_history.order_by(
                "-created_at", "-id"
            ).first()

            if (
                not latest_history
                or latest_history.status not in ("delivered", "collected")
            ):
                skipped_count += 1
                continue

            completion_date = timezone.localtime(
                latest_history.created_at
            ).date()

            if not (week_start <= completion_date <= week_end):
                skipped_count += 1
                continue

            grouped.setdefault(payout.driver_id, []).append(payout)

        for driver_id, driver_payouts in grouped.items():
            driver = driver_payouts[0].driver
            statement_number = f"AXWB-{driver.id}-{week_start:%Y%m%d}"

            batch, created = DriverPayoutBatch.objects.get_or_create(
                driver=driver,
                week_start=week_start,
                week_end=week_end,
                defaults={
                    "statement_number": statement_number,
                    "status": "pending",
                },
            )

            if created:
                created_count += 1
            elif batch.status != "pending":
                skipped_count += len(driver_payouts)
                continue

            for payout in driver_payouts:
                if payout.batch_id is not None or payout.status != "pending":
                    skipped_count += 1
                    continue

                payout.batch = batch
                payout.save(update_fields=["batch", "updated_at"])
                assigned_count += 1

            batch.total_amount = sum(
                batch.payouts.filter(status="pending").values_list(
                    "amount", flat=True
                ),
                Decimal("0.00"),
            )
            batch.save(update_fields=["total_amount", "updated_at"])

    if assigned_count:
        messages.success(
            request,
            f"Assigned {assigned_count} eligible payout(s) to "
            f"{created_count} new batch(es) for "
            f"{week_start:%d %b %Y} to {week_end:%d %b %Y}. "
            "No payments were marked paid.",
        )
    else:
        messages.info(
            request,
            "No eligible unassigned payouts were found for that week.",
        )

    if skipped_count:
        messages.warning(
            request,
            f"{skipped_count} payout(s) were skipped because their status "
            "or existing batch did not allow assignment.",
        )

    return redirect("owner_driver_payouts")


@user_passes_test(
    is_owner,
    login_url="/owner/login/"
)
def mark_driver_payout_batch_paid(request, batch_id):
    if request.method != "POST":
        return redirect("owner_driver_payouts")

    payment_reference = request.POST.get("payment_reference", "").strip()
    payment_notes = request.POST.get("payment_notes", "").strip()

    if not payment_reference:
        messages.error(request, "Enter the bank transaction reference.")
        return redirect("owner_driver_payouts")

    if request.POST.get("transfer_confirmed") != "yes":
        messages.error(
            request,
            "Confirm that the bank transfer succeeded before recording payment.",
        )
        return redirect("owner_driver_payouts")

    with transaction.atomic():
        batch = get_object_or_404(
            DriverPayoutBatch.objects.select_for_update().select_related("driver"),
            id=batch_id,
        )

        if batch.status == "paid":
            messages.info(
                request,
                f"Weekly batch {batch.statement_number} is already marked as paid.",
            )
            return redirect("owner_driver_payouts")

        driver = batch.driver

        if not driver.bank_name or not driver.account_number:
            messages.error(
                request,
                "The driver's bank details are incomplete. No payment was recorded.",
            )
            return redirect("owner_driver_payouts")

        if driver.banking_status != "verified":
            messages.error(
                request,
                "The driver's banking details must be verified. No payment was recorded.",
            )
            return redirect("owner_driver_payouts")

        payouts = list(
            DriverPayout.objects.select_for_update()
            .select_related("order")
            .filter(batch_id=batch.id)
            .order_by("id")
        )

        if not payouts:
            messages.error(
                request,
                "This batch has no payouts. No payment was recorded.",
            )
            return redirect("owner_driver_payouts")

        invalid_payouts = []

        for payout in payouts:
            latest_history = payout.order.status_history.order_by(
                "-created_at", "-id"
            ).first()

            completion_date = (
                timezone.localtime(latest_history.created_at).date()
                if latest_history else None
            )

            if (
                payout.status != "pending"
                or payout.driver_id != driver.id
                or payout.order.status not in ("delivered", "collected")
                or payout.order.payment_status != "paid"
                or not latest_history
                or latest_history.status not in ("delivered", "collected")
                or completion_date is None
                or not (batch.week_start <= completion_date <= batch.week_end)
            ):
                invalid_payouts.append(payout)

        if invalid_payouts:
            messages.error(
                request,
                "The batch contains a payout that is already paid or is no longer "
                "eligible. No records were changed; review the batch first.",
            )
            return redirect("owner_driver_payouts")

        paid_at = timezone.now()

        for payout in payouts:
            if not payout.statement_number:
                payout.statement_number = f"AXD-{payout.id:06d}"

            payout.status = "paid"
            payout.payment_reference = payment_reference
            payout.payment_notes = payment_notes
            payout.paid_at = paid_at
            payout.save(
                update_fields=[
                    "statement_number",
                    "status",
                    "payment_reference",
                    "payment_notes",
                    "paid_at",
                    "updated_at",
                ]
            )

        batch.total_amount = sum(
            (payout.amount for payout in payouts),
            Decimal("0.00"),
        )
        batch.payment_reference = payment_reference
        batch.payment_notes = payment_notes
        batch.status = "paid"
        batch.paid_at = paid_at
        batch.save(
            update_fields=[
                "total_amount",
                "payment_reference",
                "payment_notes",
                "status",
                "paid_at",
                "updated_at",
            ]
        )

    messages.success(
        request,
        f"Weekly batch {batch.statement_number} recorded as paid for "
        f"R{batch.total_amount:,.2f}. Reference: {payment_reference}",
    )
    return redirect("owner_driver_payouts")


@user_passes_test(
    is_owner,
    login_url="/owner/login/"
)
def simulate_driver_payout_batch(request, batch_id):
    """
    Validate a weekly payout batch for testing without changing any records.
    """
    if request.method != "POST":
        return redirect("owner_driver_payouts")

    batch = get_object_or_404(
        DriverPayoutBatch.objects.select_related("driver").prefetch_related(
            "payouts__order"
        ),
        id=batch_id,
    )

    if batch.status != "pending":
        messages.error(
            request,
            "Only pending batches can be simulated. No records were changed.",
        )
        return redirect("owner_driver_payouts")

    payouts = list(batch.payouts.select_related("order").order_by("id"))

    if not payouts:
        messages.error(
            request,
            "The batch has no payouts to test. No records were changed.",
        )
        return redirect("owner_driver_payouts")

    invalid_orders = []

    for payout in payouts:
        latest_history = payout.order.status_history.order_by(
            "-created_at", "-id"
        ).first()

        completion_date = (
            timezone.localtime(latest_history.created_at).date()
            if latest_history else None
        )

        if (
            payout.status != "pending"
            or payout.driver_id != batch.driver_id
            or payout.order.status not in ("delivered", "collected")
            or payout.order.payment_status != "paid"
            or not latest_history
            or latest_history.status not in ("delivered", "collected")
            or completion_date is None
            or not (batch.week_start <= completion_date <= batch.week_end)
        ):
            invalid_orders.append(payout.order_id)

    if invalid_orders:
        messages.error(
            request,
            "SIMULATION FAILED ? NO REAL PAYMENT MADE. "
            f"Review ineligible orders: {', '.join(map(str, invalid_orders))}. "
            "No records were changed.",
        )
        return redirect("owner_driver_payouts")

    simulated_total = sum(
        (payout.amount for payout in payouts),
        Decimal("0.00"),
    )

    messages.success(
        request,
        "SIMULATION PASSED ? NO REAL PAYMENT MADE. "
        f"Batch {batch.statement_number}: {len(payouts)} payouts, "
        f"total R{simulated_total:,.2f}. "
        "All payout and payment records remain unchanged.",
    )
    return redirect("owner_driver_payouts")


@user_passes_test(
    is_owner,
    login_url="/owner/login/"
)
def download_driver_payout_batch_statement(request, batch_id):
    batch = get_object_or_404(
        DriverPayoutBatch.objects.select_related("driver").prefetch_related(
            "payouts__order__shop"
        ),
        id=batch_id,
    )

    if batch.status != "paid":
        messages.error(
            request,
            "The weekly statement is available only after payment is recorded.",
        )
        return redirect("owner_driver_payouts")

    payouts = list(batch.payouts.select_related("order", "order__shop").order_by("id"))

    if not payouts:
        messages.error(request, "This batch contains no payout records.")
        return redirect("owner_driver_payouts")

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=35,
        leftMargin=35,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()

    logo_path = (
        Path(__file__).resolve().parent.parent
        / "static"
        / "orders"
        / "images"
        / "Airxpress-main-logo.png"
    )

    story = []
    if logo_path.exists():
        logo = Image(str(logo_path), width=90, height=90, kind="proportional")
        logo.hAlign = "CENTER"
        story.append(logo)
        story.append(Spacer(1, 8))

    story.extend([
        Paragraph("AIRXPRESS EATS", styles["Title"]),
        Paragraph("Weekly Driver Payment Statement", styles["Heading2"]),
        Spacer(1, 12),
    ])

    paid_date = (
        batch.paid_at.strftime("%d %B %Y at %H:%M")
        if batch.paid_at else "-"
    )

    details = [
        ["Statement Number", batch.statement_number],
        ["Driver", str(batch.driver.name)],
        ["Payout Week", f"{batch.week_start:%d %B %Y} to {batch.week_end:%d %B %Y}"],
        ["Payment Status", "Paid"],
        ["Payment Date", paid_date],
        ["Bank Transaction Reference", batch.payment_reference or "-"],
        ["Payment Notes", batch.payment_notes or "-"],
    ]

    details_table = Table(details, colWidths=[165, 335])
    details_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EAF0F6")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#172B4D")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    story.extend([
        details_table,
        Spacer(1, 18),
        Paragraph("Included Orders", styles["Heading2"]),
        Spacer(1, 8),
    ])

    order_rows = [["Order", "Shop", "Amount"]]
    for payout in payouts:
        order_rows.append([
            f"#{payout.order.id}",
            str(payout.order.shop.name),
            f"R {payout.amount:,.2f}",
        ])

    order_rows.append(["", "TOTAL PAID", f"R {batch.total_amount:,.2f}"])

    orders_table = Table(order_rows, colWidths=[65, 290, 100], repeatRows=1)
    orders_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF0F6")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (1, -1), (-1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("ALIGN", (2, 1), (2, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    story.extend([
        orders_table,
        Spacer(1, 18),
        Paragraph(
            "This statement records payment details entered in AirXpress Eats. "
            "It is not a bank-issued proof of transfer.",
            styles["Normal"],
        ),
    ])

    document.build(story)
    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="weekly-driver-statement-{batch.statement_number}.pdf"'
    )
    return response


@user_passes_test(
    is_owner,
    login_url="/owner/login/"
)
def owner_dashboard(request):
    MONTHLY_PLATFORM_FEE = Decimal("500.00")

    shops = Shop.objects.filter(
        is_active=True
    ).order_by("name")

    selected_year = request.GET.get("year")
    selected_month = request.GET.get("month")

    # =========================================================
    # LIVE PLATFORM OPERATIONS
    # =========================================================

    active_orders = Order.objects.filter(
        shop__is_active=True
    )

    live_status_counts = {
        "new": active_orders.filter(status="new").count(),
        "preparing": active_orders.filter(status="preparing").count(),
        "ready": active_orders.filter(status="ready").count(),
        "driver_assigned": active_orders.filter(status="driver_assigned").count(),
        "picked_up": active_orders.filter(status="picked_up").count(),
        "delivered": active_orders.filter(status="delivered").count(),
        "collected": active_orders.filter(status="collected").count(),
        "cancelled": active_orders.filter(status="cancelled").count(),
    }

    # =========================================================
    # MONTH SELECTION
    # =========================================================

    all_collected_orders = active_orders.filter(
        status="collected"
    )

    latest_order = (
        all_collected_orders
        .order_by("-updated_at")
        .first()
    )

    if selected_year and selected_month:
        try:
            selected_year = int(selected_year)
            selected_month = int(selected_month)

            if not 1 <= selected_month <= 12:
                raise ValueError

        except (TypeError, ValueError):
            now = timezone.now()
            selected_year = now.year
            selected_month = now.month

    elif latest_order:
        selected_year = latest_order.updated_at.year
        selected_month = latest_order.updated_at.month

    else:
        now = timezone.now()
        selected_year = now.year
        selected_month = now.month

    # =========================================================
    # SELECTED-MONTH FINANCIAL REPORT
    # =========================================================

    monthly_orders = (
        all_collected_orders
        .filter(
            updated_at__year=selected_year,
            updated_at__month=selected_month,
        )
        .select_related("shop", "driver")
        .order_by("-updated_at")
    )

    total_orders = monthly_orders.count()

    total_transaction_value = sum(
        (
            order.final_total
            if order.final_total is not None
            else order.estimated_total
        )
        for order in monthly_orders
    ) or Decimal("0.00")

    total_delivery_fees = sum(
        (
            order.delivery_fee
            if order.delivery_fee is not None
            else Decimal("0.00")
        )
        for order in monthly_orders
    ) or Decimal("0.00")

    total_transaction_platform_fees = sum(
        (
            order.platform_fee
            if order.platform_fee is not None
            else Decimal("0.00")
        )
        for order in monthly_orders
    ) or Decimal("0.00")

    total_driver_payouts = sum(
        (
            order.driver_payout
            if order.driver_payout is not None
            else Decimal("0.00")
        )
        for order in monthly_orders
    ) or Decimal("0.00")

    net_platform_earnings = (
        total_transaction_platform_fees
        - total_driver_payouts
    )

    # =========================================================
    # PAYMENT MONITORING
    # =========================================================

    payment_counts = {
        "paid": active_orders.filter(payment_status="paid").count(),
        "pending": active_orders.filter(payment_status="pending").count(),
        "failed": active_orders.filter(payment_status="failed").count(),
        "refunded": active_orders.filter(payment_status="refunded").count(),
    }

    # =========================================================
    # DRIVER MONITORING
    # =========================================================

    all_drivers = Driver.objects.all()

    total_drivers = all_drivers.count()

    verified_drivers = all_drivers.filter(
        airxpress_verified=True
    ).count()

    pending_drivers = all_drivers.filter(
        license_verification_status="pending"
    ).count()

    # =========================================================
    # OWNER DRIVER VERIFICATION QUEUE
    # Only drivers awaiting AirXpress verification.
    # =========================================================

    driver_verification_list = (
        all_drivers
        .filter(
            license_verification_status="pending"
        )
        .order_by(
            "name"
        )
    )

    # =========================================================
    # All active-shop drivers for owner password management.
    driver_password_reset_list = (
        all_drivers
        .select_related("user")
        .order_by("name")
    )

    # Active shop staff accounts available for owner password management.
    staff_password_reset_list = (
        StaffProfile.objects
        .filter(
            shop__is_active=True,
            is_active=True,
            user__is_active=True,
        )
        .select_related("shop", "user")
        .order_by("shop__name", "user__username")
    )
    # Active customer accounts available for owner password management.
    customer_password_reset_list = (
        CustomerProfile.objects
        .filter(user__is_active=True)
        .select_related("user")
        .order_by("user__username")
    )
    # SHOP SUBSCRIPTIONS
    # =========================================================

    shop_summaries = []

    total_subscription_fees = Decimal("0.00")
    paid_platform_fees = Decimal("0.00")

    for shop in shops:

        shop_orders = [
            order
            for order in monthly_orders
            if order.shop_id == shop.id
        ]

        shop_transaction_value = sum(
            (
                order.final_total
                if order.final_total is not None
                else order.estimated_total
            )
            for order in shop_orders
        ) or Decimal("0.00")

        shop_transaction_platform_fees = sum(
            (
                order.platform_fee
                if order.platform_fee is not None
                else Decimal("0.00")
            )
            for order in shop_orders
        ) or Decimal("0.00")

        subscription, created = ShopSubscriptionPayment.objects.get_or_create(
            shop=shop,
            year=selected_year,
            month=selected_month,
            defaults={
                "amount": MONTHLY_PLATFORM_FEE,
            },
        )

        shop_subscription_fee = subscription.amount

        shop_paid_fees = (
            subscription.amount
            if subscription.is_paid
            else Decimal("0.00")
        )

        shop_outstanding_fees = (
            Decimal("0.00")
            if subscription.is_paid
            else subscription.amount
        )

        total_subscription_fees += shop_subscription_fee
        paid_platform_fees += shop_paid_fees

        shop_summaries.append({
            "shop": shop,
            "total_orders": len(shop_orders),
            "transaction_value": shop_transaction_value,
            "transaction_platform_fees": shop_transaction_platform_fees,
            "platform_fees": shop_subscription_fee,
            "paid_fees": shop_paid_fees,
            "outstanding_fees": shop_outstanding_fees,
        })

    outstanding_platform_fees = (
        total_subscription_fees - paid_platform_fees
    )

    # =========================================================
    # MONTH OPTIONS
    # =========================================================

    available_months = (
        Order.objects
        .filter(
            shop__is_active=True,
            status="collected",
        )
        .dates(
            "updated_at",
            "month",
            order="DESC",
        )
    )

    context = {
        "connected_shops": shops.count(),

        # Live operations
        "live_status_counts": live_status_counts,

        # Selected-month financials
        "total_orders": total_orders,
        "total_transaction_value": total_transaction_value,
        "total_delivery_fees": total_delivery_fees,
        "total_transaction_platform_fees": total_transaction_platform_fees,
        "total_driver_payouts": total_driver_payouts,
        "net_platform_earnings": net_platform_earnings,

        # Payment monitoring
        "payment_counts": payment_counts,

        # Driver monitoring
        "total_drivers": total_drivers,
        "verified_drivers": verified_drivers,
        "pending_drivers": pending_drivers,
        "driver_verification_list": driver_verification_list,
        "driver_password_reset_list": driver_password_reset_list,
        "staff_password_reset_list": staff_password_reset_list,
        "customer_password_reset_list": customer_password_reset_list,

        # Shop subscriptions
        "total_platform_fees": total_subscription_fees,
        "paid_platform_fees": paid_platform_fees,
        "outstanding_platform_fees": outstanding_platform_fees,

        "shop_summaries": shop_summaries,
        "available_months": available_months,
        "selected_year": selected_year,
        "selected_month": selected_month,
    }

    return render(
        request,
        "orders/owner_dashboard.html",
        context
    )

@user_passes_test(
    is_owner,
    login_url="/owner/login/"
)


# =========================================================
# OWNER / AIRXPRESS DRIVER PASSWORD RESET
# =========================================================

@user_passes_test(
    is_owner,
    login_url="/owner/login/"
)
def owner_reset_driver_password(request, driver_id):
    if request.method != "POST":
        return redirect("owner_dashboard")

    driver = get_object_or_404(
        Driver,
        id=driver_id,
    )

    if not driver.user:
        messages.error(
            request,
            f"{driver.name} does not have a linked login account.",
        )
        return redirect("owner_dashboard")

    password = request.POST.get("new_password", "")
    confirm_password = request.POST.get("confirm_password", "")

    if not password or password != confirm_password:
        messages.error(
            request,
            "The passwords are empty or do not match. Please try again.",
        )
        return redirect("owner_dashboard")

    try:
        validate_password(password, user=driver.user)
    except ValidationError as exc:
        for error in exc.messages:
            messages.error(request, error)
        return redirect("owner_dashboard")

    driver.user.set_password(password)
    driver.user.save(update_fields=["password"])

    messages.success(
        request,
        f"Password reset successfully for driver {driver.name}. Share the new password privately.",
    )
    return redirect("owner_dashboard")

# =========================================================

@user_passes_test(
    is_owner,
    login_url="/owner/login/"
)
def owner_reset_staff_password(request, staff_id):
    if request.method != "POST":
        return redirect("owner_dashboard")

    staff_profile = get_object_or_404(
        StaffProfile.objects.select_related("user", "shop"),
        id=staff_id,
        shop__is_active=True,
        is_active=True,
    )

    staff_user = staff_profile.user
    password = request.POST.get("new_password", "")
    confirm_password = request.POST.get("confirm_password", "")

    if not password or password != confirm_password:
        messages.error(
            request,
            "The passwords are empty or do not match. Please try again.",
        )
        return redirect("owner_dashboard")

    try:
        validate_password(password, user=staff_user)
    except ValidationError as exc:
        for error in exc.messages:
            messages.error(request, error)
        return redirect("owner_dashboard")

    staff_user.set_password(password)
    staff_user.save(update_fields=["password"])

    messages.success(
        request,
        f"Password reset successfully for shop staff {staff_user.username}.",
    )
    return redirect("owner_dashboard")
@user_passes_test(
    is_owner,
    login_url="/owner/login/"
)
def owner_reset_customer_password(request, customer_id):
    """Set a temporary password and require the customer to change it."""
    if request.method != "POST":
        return redirect("owner_dashboard")

    profile = get_object_or_404(
        CustomerProfile.objects.select_related("user"),
        id=customer_id,
        user__is_active=True,
    )

    customer = profile.user
    password = request.POST.get("new_password", "")
    confirm_password = request.POST.get("confirm_password", "")

    if not password or password != confirm_password:
        messages.error(
            request,
            "The temporary passwords are empty or do not match.",
        )
        return redirect("owner_dashboard")

    try:
        validate_password(password, user=customer)
    except ValidationError as exc:
        for error in exc.messages:
            messages.error(request, error)
        return redirect("owner_dashboard")

    customer.set_password(password)
    customer.save(update_fields=["password"])

    profile.must_change_password = True
    profile.save(update_fields=["must_change_password"])

    messages.success(
        request,
        f"Temporary password set for customer {customer.username}. "
        "Share it privately. The customer must change it at their next login.",
    )
    return redirect("owner_dashboard")

# OWNER / AIRXPRESS DRIVER VERIFICATION
# =========================================================

@user_passes_test(
    is_owner,
    login_url="/owner/login/"
)

@user_passes_test(is_owner, login_url="/owner/login/")
def owner_add_driver(request):
    if request.method != "POST":
        return redirect("owner_dashboard")

    from django.contrib.auth import get_user_model
    from django.db import transaction

    UserModel = get_user_model()
    name = request.POST.get("name", "").strip()
    username = request.POST.get("username", "").strip()
    password = request.POST.get("password", "")
    confirm_password = request.POST.get("confirm_password", "")
    vehicle_make_model = request.POST.get("vehicle_make_model", "").strip()
    vehicle_colour = request.POST.get("vehicle_colour", "").strip()
    vehicle_registration = request.POST.get("vehicle_registration", "").strip().upper()

    if not all([name, username, password, confirm_password]):
        messages.error(request, "Name, username and both password fields are required.")
        return redirect("owner_dashboard")

    if password != confirm_password:
        messages.error(request, "The passwords do not match.")
        return redirect("owner_dashboard")

    if UserModel.objects.filter(username__iexact=username).exists():
        messages.error(request, "That username is already in use.")
        return redirect("owner_dashboard")

    if Driver.objects.filter(name__iexact=name).exists():
        messages.error(request, "A driver with that name already exists.")
        return redirect("owner_dashboard")

    try:
        user = UserModel(username=username, first_name=name.split()[0])
        validate_password(password, user=user)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("owner_dashboard")

    try:
        with transaction.atomic():
            user = UserModel.objects.create_user(
                username=username,
                password=password,
                first_name=name.split()[0],
            )
            Driver.objects.create(
                user=user,
                name=name,
                vehicle_make_model=vehicle_make_model,
                vehicle_colour=vehicle_colour,
                vehicle_registration=vehicle_registration,
                license_verification_status="pending",
                airxpress_verified=False,
            )
    except Exception:
        messages.error(request, "Driver registration failed. No account was created; check the server log.")
        raise

    messages.success(
        request,
        f"Driver account created for {name}. Licence verification is still pending. Share the login details privately.",
    )
    return redirect("owner_dashboard")

def owner_verify_driver(request, driver_id):

    if request.method != "POST":
        return redirect("owner_dashboard")

    driver = get_object_or_404(
        Driver,
        id=driver_id,
    )

    action = request.POST.get(
        "action",
        ""
    ).strip().lower()

    if action == "verify":

        if not driver.driver_license:
            messages.error(
                request,
                "This driver cannot be verified because no driver licence has been uploaded.",
            )
            return redirect("owner_dashboard")

        driver.license_verification_status = "verified"
        driver.airxpress_verified = True

        driver.save(
            update_fields=[
                "license_verification_status",
                "airxpress_verified",
            ]
        )

        messages.success(
            request,
            f"{driver.name} has been verified as an AirXpress driver.",
        )

    elif action == "reject":

        driver.license_verification_status = "rejected"
        driver.airxpress_verified = False

        driver.save(
            update_fields=[
                "license_verification_status",
                "airxpress_verified",
            ]
        )

        messages.warning(
            request,
            f"{driver.name}'s driver licence has been rejected.",
        )

    else:

        messages.error(
            request,
            "Invalid driver verification action.",
        )

    return redirect("owner_dashboard")

def mark_platform_fees_paid(request):
    if request.method != "POST":
        return redirect("owner_dashboard")

    try:
        shop_id = int(request.POST.get("shop_id"))
        year = int(request.POST.get("year"))
        month = int(request.POST.get("month"))

        if not 1 <= month <= 12:
            raise ValueError

    except (TypeError, ValueError):
        return redirect("owner_dashboard")

    shop = get_object_or_404(
        Shop,
        id=shop_id,
        is_active=True,
    )

    subscription, created = ShopSubscriptionPayment.objects.get_or_create(
        shop=shop,
        year=year,
        month=month,
        defaults={
            "amount": Decimal("500.00"),
        },
    )

    subscription.is_paid = True
    subscription.paid_at = timezone.now()
    subscription.save(
        update_fields=[
            "is_paid",
            "paid_at",
            "updated_at",
        ]
    )

    return redirect(
        f"/owner/dashboard/?year={year}&month={month}"
    )























































# =========================================================
# PAYFAST PAYMENT
# =========================================================

@csrf_exempt
def payfast_itn(request):
    """
    Receive and process PayFast Instant Transaction Notifications.

    Orders remain pending until PayFast confirms the payment.
    """

    if request.method != "POST":
        return JsonResponse(
            {"status": "method_not_allowed"},
            status=405,
        )

    payment_data = request.POST.dict()

    # Reject notifications without a valid PayFast signature.
    from .payfast import validate_itn_signature, validate_itn_with_payfast

    if not validate_itn_signature(payment_data):
        return JsonResponse(
            {"status": "invalid_signature"},
            status=400,
        )

    # Confirm the notification directly with PayFast.
    if not validate_itn_with_payfast(payment_data):
        return JsonResponse(
            {"status": "payfast_validation_failed"},
            status=400,
        )

    received_merchant_id = str(payment_data.get("merchant_id", "")).strip()
    expected_merchant_id = str(settings.PAYFAST_MERCHANT_ID).strip()

    if not received_merchant_id or received_merchant_id != expected_merchant_id:
        return JsonResponse(
            {"status": "merchant_mismatch"},
            status=400,
        )

    order_id = payment_data.get("m_payment_id")

    if not order_id:
        return JsonResponse(
            {"status": "missing_payment_id"},
            status=400,
        )

    try:
        order_id = int(order_id)
    except (TypeError, ValueError):
        return JsonResponse(
            {"status": "invalid_payment_id"},
            status=400,
        )

    try:
        order = Order.objects.get(
            id=order_id,
        )
    except Order.DoesNotExist:
        return JsonResponse(
            {"status": "order_not_found"},
            status=404,
        )

    try:
        paid_amount = Decimal(
            str(
                payment_data.get(
                    "amount_gross",
                    payment_data.get("amount", "0.00"),
                )
            )
        )
    except (InvalidOperation, TypeError, ValueError):
        return JsonResponse(
            {"status": "invalid_amount"},
            status=400,
        )

    expected_amount = (
        order.final_total or Decimal("0.00")
    )

    if paid_amount != expected_amount:
        return JsonResponse(
            {"status": "amount_mismatch"},
            status=400,
        )

    payment_status = payment_data.get(
        "payment_status",
        "",
    ).lower()

    print(
        "PAYFAST ITN DEBUG:",
        {
            "order_id": order_id,
            "received_amount": str(paid_amount),
            "expected_amount": str(expected_amount),
            "payment_status": payment_status,
        },
    )

    if payment_status != "complete":
        return JsonResponse(
            {"status": "payment_not_complete"},
            status=200,
        )

    with transaction.atomic():
        order = (
            Order.objects
            .select_for_update()
            .get(id=order.id)
        )

        if order.payment_status != "paid":
            order.payment_status = "paid"

            order.save(
                update_fields=[
                    "payment_status",
                    "updated_at",
                ]
            )

            OrderStatusHistory.objects.create(
                order=order,
                status=order.status,
                notes=(
                    f"PayFast payment confirmed for "
                    f"Order #{order.id}."
                ),
            )

            # =============================================
            # AUTOMATIC DRIVER DISPATCH AFTER PAYMENT
            # =============================================
            # If payment is confirmed after the shop has
            # already marked the order Ready, dispatch it.
            # =============================================

            if (
                order.status == "ready"
                and order.order_type == "delivery"
                and not order.driver_id
            ):
                dispatch_order_to_available_drivers(order)

    return JsonResponse(
        {"status": "payment_confirmed"},
        status=200,
    )

def payfast_payment(request, order_id):
    """
    Start the PayFast payment process for an existing order.

    The order must remain pending until PayFast confirms
    the transaction through ITN.
    """
    order = get_object_or_404(
        Order.objects.select_related("shop"),
        id=order_id,
    )

    if order.payment_status == "paid":
        return redirect(
            "order_success",
            shop_slug=order.shop.slug,
            order_id=order.id,
        )

    if not order.final_total or order.final_total <= Decimal("0.00"):
        messages.error(
            request,
            "This order does not have a valid payment amount.",
        )
        return redirect(
            "order_success",
            shop_slug=order.shop.slug,
            order_id=order.id,
        )

    return_url = request.build_absolute_uri(
        reverse(
            "order_success",
            kwargs={
                "shop_slug": order.shop.slug,
                "order_id": order.id,
            },
        )
    )

    cancel_url = request.build_absolute_uri(
        reverse(
            "order_success",
            kwargs={
                "shop_slug": order.shop.slug,
                "order_id": order.id,
            },
        )
    )

    notify_url = (
        settings.PAYFAST_PUBLIC_URL.rstrip("/")
        + reverse("payfast_itn")
    )

    from .payfast import (
        get_payfast_url,
        build_payment_data,
    )

    payment_data = build_payment_data(
        order=order,
        return_url=return_url,
        cancel_url=cancel_url,
        notify_url=notify_url,
    )

    return render(
        request,
        "orders/payfast_payment.html",
        {
            "payfast_url": get_payfast_url(),
            "payment_data": payment_data,
            "order": order,
        },
    )



















































# =========================================================
# STAFF DASHBOARD AJAX UPDATES
# =========================================================

@login_required(login_url="/staff/login/")
@user_passes_test(
    is_tenant_staff,
    login_url="/staff/login/"
)
def staff_dashboard_updates(request):

    shop = get_user_shop(request.user)

    if not shop:
        return JsonResponse(
            {"success": False},
            status=403,
        )

    orders = (
        Order.objects
        .filter(shop=shop)
        .exclude(
            status__in=[
                "delivered",
                "collected",
                "cancelled",
            ]
        )
        .prefetch_related("items__menu_item")
        .order_by("-created_at")
    )

    drivers = (
        Driver.objects
        .filter(
            is_available=True,
            airxpress_verified=True,
            license_verification_status="verified",
        )
        .order_by("name")
    )

    context = {
        "shop": shop,
        "orders": orders,
        "drivers": drivers,
        "new_orders": orders.filter(
            status="new"
        ).count(),
        "preparing_orders": orders.filter(
            status="preparing"
        ).count(),
        "ready_orders": orders.filter(
            status="ready"
        ).count(),
        "driver_assigned_orders": orders.filter(
            status="driver_assigned"
        ).count(),
        "picked_up_orders": orders.filter(
            status="picked_up"
        ).count(),
        "on_the_way_orders": orders.filter(
            status="on_the_way"
        ).count(),
    }

    return render(
        request,
        "orders/staff_dashboard_updates.html",
        context,
    )




# =========================================================

# =========================================================
# SHOP PAYOUT TEST SIMULATION - READ ONLY
# =========================================================

@user_passes_test(is_owner, login_url="/owner/login/")
def simulate_shop_payouts(request):
    from datetime import date, timedelta
    from decimal import ROUND_HALF_UP

    if request.method != "POST":
        return redirect("owner_shop_payouts")

    try:
        week_start = date.fromisoformat(request.POST.get("week_start", ""))
    except (ValueError, TypeError):
        messages.error(request, "Simulation failed: select a valid Monday.")
        return redirect("owner_shop_payouts")

    if week_start.weekday() != 0:
        messages.error(request, "Simulation failed: the week must start on Monday.")
        return redirect("owner_shop_payouts")

    week_end = week_start + timedelta(days=6)
    eligible_count = 0
    blocked_count = 0
    total_sales = Decimal("0.00")
    total_commission = Decimal("0.00")
    total_shop_payable = Decimal("0.00")
    shop_totals = {}

    orders = (
        Order.objects.filter(
            status__in=["delivered", "collected"],
            payment_status="paid",
        )
        .select_related("shop")
        .prefetch_related("items")
        .order_by("shop__name", "id")
    )

    for order in orders:
        latest_history = (
            OrderStatusHistory.objects.filter(order=order)
            .order_by("-created_at", "-id")
            .first()
        )

        if (
            not latest_history
            or latest_history.status not in ["delivered", "collected"]
        ):
            continue

        completed_date = timezone.localtime(
            latest_history.created_at
        ).date()

        if not (week_start <= completed_date <= week_end):
            continue

        food_sales = sum(
            (
                item.final_amount
                if item.final_amount is not None
                else item.requested_amount
                if item.requested_amount is not None
                else item.unit_price or Decimal("0.00")
            )
            for item in order.items.all()
        )
        food_sales = Decimal(food_sales or 0).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        if food_sales <= Decimal("0.00"):
            blocked_count += 1
            continue

        existing = ShopPayout.objects.filter(order=order).first()
        if existing:
            blocked_count += 1
            continue

        commission = (food_sales * Decimal("0.15")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        shop_amount = (food_sales - commission).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        shop_key = order.shop_id
        if shop_key not in shop_totals:
            shop_totals[shop_key] = {
                "name": order.shop.name,
                "orders": 0,
                "sales": Decimal("0.00"),
                "commission": Decimal("0.00"),
                "payable": Decimal("0.00"),
            }

        shop_totals[shop_key]["orders"] += 1
        shop_totals[shop_key]["sales"] += food_sales
        shop_totals[shop_key]["commission"] += commission
        shop_totals[shop_key]["payable"] += shop_amount

        eligible_count += 1
        total_sales += food_sales
        total_commission += commission
        total_shop_payable += shop_amount

    lines = [
        f"{value['name']}: {value['orders']} orders, "
        f"food sales R{value['sales']:.2f}, "
        f"commission R{value['commission']:.2f}, "
        f"shop payable R{value['payable']:.2f}"
        for value in shop_totals.values()
    ]

    if eligible_count:
        messages.success(
            request,
            "SIMULATION PASSED - NO PAYOUT RECORDS CHANGED AND NO MONEY PAID. "
            f"Week {week_start} to {week_end}. "
            f"Eligible orders: {eligible_count}; blocked/already recorded: "
            f"{blocked_count}; food sales R{total_sales:.2f}; "
            f"AirXpress commission R{total_commission:.2f}; "
            f"shop payable R{total_shop_payable:.2f}. "
            + " | ".join(lines)
        )
    else:
        messages.info(
            request,
            "SIMULATION COMPLETE - NO PAYOUT RECORDS CHANGED AND NO MONEY PAID. "
            f"No new eligible orders were found for {week_start} to {week_end}. "
            f"Orders already recorded or with invalid food totals were skipped."
        )

    return redirect("owner_shop_payouts")
# SHOP WEEKLY PAYOUT MANAGEMENT
# =========================================================

@user_passes_test(is_owner, login_url="/owner/login/")
def download_shop_payout_batch_statement(request, batch_id):
    batch = get_object_or_404(
        ShopPayoutBatch.objects.select_related("shop").prefetch_related(
            "payouts__order"
        ),
        id=batch_id,
    )

    payouts = list(
        batch.payouts.select_related("order", "order__shop").order_by("order_id")
    )

    if not payouts:
        messages.error(request, "This shop batch contains no payout records.")
        return redirect("owner_shop_payouts")

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=35,
        leftMargin=35,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()
    payment_status = "PAID" if batch.status == "paid" else "NOT PAID"
    paid_date = (
        timezone.localtime(batch.paid_at).strftime("%d %B %Y at %H:%M")
        if batch.paid_at else "-"
    )

    logo_path = (
        Path(__file__).resolve().parent.parent
        / "static"
        / "orders"
        / "images"
        / "Airxpress-main-logo.png"
    )

    story = []

    if logo_path.exists():
        logo = Image(str(logo_path), width=90, height=90, kind="proportional")
        logo.hAlign = "CENTER"
        story.append(logo)
        story.append(Spacer(1, 8))

    story.extend([
        Paragraph("AIRXPRESS EATS", styles["Title"]),
        Paragraph("Weekly Shop Payment Statement", styles["Heading2"]),
        Spacer(1, 12),
    ])

    details = [
        ["Statement Number", batch.statement_number],
        ["Shop", str(batch.shop.name)],
        ["Payout Week", f"{batch.week_start:%d %B %Y} to {batch.week_end:%d %B %Y}"],
        ["Payment Status", payment_status],
        ["Payment Date", paid_date],
        ["Bank Transaction Reference", batch.payment_reference or "-"],
        ["Payment Notes", batch.payment_notes or "-"],
    ]

    details_table = Table(details, colWidths=[165, 335])
    details_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EAF0F6")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#172B4D")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    story.extend([
        details_table,
        Spacer(1, 18),
        Paragraph("Included Orders", styles["Heading2"]),
        Spacer(1, 8),
    ])

    order_rows = [["Order", "Food Sales", "Commission", "Shop Receives"]]
    for payout in payouts:
        order_rows.append([
            f"#{payout.order_id}",
            f"R {payout.food_sales:,.2f}",
            f"R {payout.commission:,.2f}",
            f"R {payout.amount:,.2f}",
        ])

    order_rows.append([
        "",
        f"R {batch.total_food_sales:,.2f}",
        f"R {batch.total_commission:,.2f}",
        f"R {batch.total_amount:,.2f}",
    ])

    orders_table = Table(
        order_rows,
        colWidths=[65, 130, 130, 130],
        repeatRows=1,
    )
    orders_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF0F6")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    story.extend([
        orders_table,
        Spacer(1, 12),
        Paragraph(
            "AirXpress commission is 15% of food sales. The shop receives "
            "the remaining 85%, subject to the figures recorded in this batch.",
            styles["Normal"],
        ),
        Spacer(1, 12),
        Paragraph(
            (
                "PAYMENT HAS NOT BEEN RECORDED AS PAID. No bank transfer is "
                "confirmed by this statement."
            ) if batch.status != "paid" else (
                "This statement records payment details entered in AirXpress Eats. "
                "It is not a bank-issued proof of transfer."
            ),
            styles["Normal"],
        ),
    ])

    document.build(story)
    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="shop-payment-{batch.statement_number}.pdf"'
    )
    return response

@user_passes_test(is_owner, login_url="/owner/login/")
def owner_shop_payouts(request):
    from datetime import date, datetime, time, timedelta
    from decimal import ROUND_HALF_UP

    today = timezone.localdate()
    default_start = today - timedelta(days=today.weekday())
    selected_start = default_start
    errors = []

    if request.method == "POST":
        try:
            selected_start = date.fromisoformat(
                request.POST.get("week_start", "")
            )
        except (ValueError, TypeError):
            selected_start = None

        if selected_start is None:
            messages.error(request, "Please select a valid Monday.")
            return redirect("owner_shop_payouts")

        if selected_start.weekday() != 0:
            messages.error(request, "The week must start on a Monday.")
            return redirect("owner_shop_payouts")

        selected_end = selected_start + timedelta(days=6)

        with transaction.atomic():
            shops = Shop.objects.filter(is_active=True).order_by("name")

            for shop in shops:
                eligible_orders = Order.objects.filter(
                    shop=shop,
                    status__in=["delivered", "collected"],
                    payment_status="paid",
                ).prefetch_related("items").order_by("id")

                for order in eligible_orders:
                    completion = (
                        OrderStatusHistory.objects.filter(
                            order=order,

                        ).order_by("-created_at", "-id").first()
                    )

                    if (
                        not completion
                        or completion.status not in ("delivered", "collected")
                    ):
                        continue

                    completion_date = timezone.localtime(
                        completion.created_at
                    ).date()

                    if not (selected_start <= completion_date <= selected_end):
                        continue

                    food_sales = sum(
                        (
                            item.final_amount
                            if item.final_amount is not None
                            else item.requested_amount
                            if item.requested_amount is not None
                            else item.unit_price or Decimal("0.00")
                        )
                        for item in order.items.all()
                    )
                    food_sales = Decimal(food_sales or 0).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )

                    if food_sales <= Decimal("0.00"):
                        continue

                    payout, created = ShopPayout.objects.get_or_create(
                        order=order,
                        defaults={
                            "shop": shop,
                            "food_sales": food_sales,
                            "commission": (
                                food_sales * Decimal("0.15")
                            ).quantize(
                                Decimal("0.01"),
                                rounding=ROUND_HALF_UP,
                            ),
                            "amount": (
                                food_sales * Decimal("0.85")
                            ).quantize(
                                Decimal("0.01"),
                                rounding=ROUND_HALF_UP,
                            ),
                            "statement_number": f"AXSP-{order.id}",
                        },
                    )

                    if payout.shop_id != shop.id:
                        raise ValueError(
                            f"Shop mismatch on order #{order.id}."
                        )

                    if payout.batch_id and (
                        payout.batch.week_start != selected_start
                        or payout.batch.week_end != selected_end
                    ):
                        continue

                weekly_payouts = ShopPayout.objects.filter(
                    shop=shop,
                    order__status__in=["delivered", "collected"],
                    order__payment_status="paid",
                    batch__isnull=True,
                    status="pending",
                )

                eligible_ids = []
                for payout in weekly_payouts.select_related("order"):
                    completion = (
                        OrderStatusHistory.objects.filter(
                            order=payout.order,

                        ).order_by("-created_at", "-id").first()
                    )
                    if (
                        completion
                        and completion.status in ("delivered", "collected")
                    ):
                        completion_date = timezone.localtime(
                            completion.created_at
                        ).date()
                        if selected_start <= completion_date <= selected_end:
                            eligible_ids.append(payout.id)

                if not eligible_ids:
                    continue

                batch, _ = ShopPayoutBatch.objects.get_or_create(
                    shop=shop,
                    week_start=selected_start,
                    week_end=selected_end,
                    defaults={
                        "statement_number": (
                            f"AXSB-{shop.id}-{selected_start:%Y%m%d}"
                        ),
                    },
                )

                if batch.status == "paid":
                    continue

                ShopPayout.objects.filter(
                    id__in=eligible_ids,
                    batch__isnull=True,
                    status="pending",
                ).update(batch=batch)

                batch_payouts = batch.payouts.all()
                batch.total_food_sales = (
                    batch_payouts.aggregate(total=Sum("food_sales"))["total"]
                    or Decimal("0.00")
                )
                batch.total_commission = (
                    batch_payouts.aggregate(total=Sum("commission"))["total"]
                    or Decimal("0.00")
                )
                batch.total_amount = (
                    batch_payouts.aggregate(total=Sum("amount"))["total"]
                    or Decimal("0.00")
                )
                batch.save(update_fields=[
                    "total_food_sales",
                    "total_commission",
                    "total_amount",
                    "updated_at",
                ])

        messages.success(
            request,
            "Weekly shop batches prepared. No bank payments were made."
        )
        return redirect("owner_shop_payouts")

    from datetime import timedelta
    batches = (
        ShopPayoutBatch.objects
        .select_related("shop")
        .prefetch_related("payouts__order")
        .order_by("-week_start", "shop__name")
    )

    return render(
        request,
        "orders/owner_shop_payouts.html",
        {
            "batches": batches,
            "default_week_start": default_start.isoformat(),
            "selected_week_start": selected_start.isoformat(),
        },
    )


# =========================================================
# DRIVER WEB PUSH SUBSCRIPTIONS
# =========================================================

@user_passes_test(
    lambda user: user.is_authenticated and hasattr(user, "driver_profile"),
    login_url="/driver/login/",
)
def driver_push_vapid_public_key(request):
    """Return only the public VAPID key to an authenticated driver."""
    public_key = getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", "").strip()
    if not public_key:
        return JsonResponse(
            {"error": "Push notifications are not configured yet."},
            status=503,
        )
    return JsonResponse({"publicKey": public_key})


@user_passes_test(
    lambda user: user.is_authenticated and hasattr(user, "driver_profile"),
    login_url="/driver/login/",
)
@require_POST
def driver_push_subscribe(request):
    """Save or refresh the signed-in driver's browser push subscription."""
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    endpoint = data.get("endpoint")
    keys = data.get("keys")
    if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
        return JsonResponse({"error": "Invalid push endpoint."}, status=400)
    if len(endpoint) > 4000 or not isinstance(keys, dict):
        return JsonResponse({"error": "Invalid subscription data."}, status=400)

    p256dh = keys.get("p256dh")
    auth_key = keys.get("auth")
    if not all(isinstance(value, str) and value for value in (p256dh, auth_key)):
        return JsonResponse({"error": "Subscription keys are missing."}, status=400)
    if len(p256dh) > 500 or len(auth_key) > 500:
        return JsonResponse({"error": "Subscription keys are too long."}, status=400)

    try:
        subscription, created = DriverPushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={
                "driver": request.user.driver_profile,
                "p256dh": p256dh,
                "auth": auth_key,
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:500],
            },
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "Could not save driver push subscription."
        )
        return JsonResponse(
            {"error": "Could not save notification settings."},
            status=500,
        )

    return JsonResponse({"ok": True, "created": created})


@user_passes_test(
    lambda user: user.is_authenticated and hasattr(user, "driver_profile"),
    login_url="/driver/login/",
)
@require_POST
def driver_push_unsubscribe(request):
    """Remove only a push endpoint belonging to the signed-in driver."""
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    endpoint = data.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
        return JsonResponse({"error": "Invalid push endpoint."}, status=400)

    deleted, _ = DriverPushSubscription.objects.filter(
        driver=request.user.driver_profile,
        endpoint=endpoint,
    ).delete()

    return JsonResponse({"ok": True, "removed": bool(deleted)})


# =========================================================
# ROOT-SCOPED DRIVER PUSH SERVICE WORKER
# =========================================================

def driver_push_service_worker(request):
    """Serve the driver service worker at the site root."""
    from pathlib import Path

    worker_path = Path(settings.BASE_DIR) / "static" / "driver-push-sw.js"
    try:
        worker_code = worker_path.read_text(encoding="utf-8")
    except OSError:
        return HttpResponse("Service worker unavailable.", status=404)

    response = HttpResponse(
        worker_code,
        content_type="application/javascript; charset=utf-8",
    )
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response

