import math
from decimal import Decimal, InvalidOperation
from django.contrib.auth.password_validation import validate_password

from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib import messages

from django.contrib.auth import (
    authenticate,
    login,
    logout,
)

from django.contrib.auth.decorators import (
    login_required,
    user_passes_test,

)

from django.views.decorators.csrf import csrf_exempt

from django.http import JsonResponse
from django.shortcuts import (
    render,
    redirect,
    get_object_or_404,
)

from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, Count, Avg
from django.urls import reverse

from .forms import (
    CustomerOrderForm,
)

from .models import (
    Driver,
    DriverPayout,
    DeliveryRequest,
    DeliveryRate,
    MenuItem,
    Order,
    OrderItem,
    OrderStatusHistory,
    OrderReview,
    Shop,
    StaffProfile,
    ShopSubscriptionPayment
)

from .mapbox import MapboxError, calculate_driving_distance, calculate_driver_route
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


def home(request):
    """
    Public AirXpress Eats marketplace homepage.
    Customers can discover active businesses without logging in.
    """
    shops = Shop.objects.filter(
        is_active=True
    ).order_by("name")

    # =========================================================
    context = {
        "shops": shops[:6],
        "total_shops": shops.count(),
    }

    return render(
        request,
        "orders/home.html",
        context,
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

    cart = request.session.get("cart", {})

    item_key = str(menu_item.id)

    if menu_item.pricing_type == "fixed":

        try:
            quantity = int(
                request.POST.get(
                    "quantity",
                    "1",
                )
            )
        except (TypeError, ValueError):
            quantity = 1

        if quantity < 1:
            quantity = 1

        if item_key in cart:
            cart[item_key]["quantity"] += quantity
        else:
            cart[item_key] = {
                "quantity": quantity,
            }

    else:

        amount = request.POST.get(
            "amount",
            ""
        ).strip()

        try:
            amount_value = Decimal(amount)
        except (
            InvalidOperation,
            TypeError,
            ValueError,
        ):
            error_message = "Please enter a valid amount."

            if is_ajax:
                return JsonResponse(
                    {
                        "success": False,
                        "message": error_message,
                    },
                    status=400,
                )

            messages.error(
                request,
                error_message,
            )

            return redirect(
                "customer_order",
                shop_slug=shop.slug,
            )

        if amount_value <= 0:

            error_message = (
                "Please enter an amount greater than zero."
            )

            if is_ajax:
                return JsonResponse(
                    {
                        "success": False,
                        "message": error_message,
                    },
                    status=400,
                )

            messages.error(
                request,
                error_message,
            )

            return redirect(
                "customer_order",
                shop_slug=shop.slug,
            )

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
        return JsonResponse(
            {
                "success": True,
                "message": message,
                "cart_count": cart_count,
            }
        )

    messages.success(
        request,
        message,
    )

    return redirect(
        "customer_order",
        shop_slug=shop.slug,
    )

def cart(request, shop_slug):

    shop = get_object_or_404(
        Shop,
        slug=shop_slug,
        is_active=True,
    )

    cart_data = request.session.get("cart", {})
    cart_items = []
    subtotal = Decimal("0.00")

    for item_id, cart_item in cart_data.items():

        menu_item = MenuItem.objects.filter(
            id=item_id,
            shop=shop,
            is_available=True,
        ).first()

        if not menu_item:
            continue

        quantity = int(
            cart_item.get("quantity", 1)
        )

        if menu_item.pricing_type == "fixed":

            unit_price = menu_item.price or Decimal("0.00")
            line_total = unit_price * quantity

            cart_items.append({
                "menu_item": menu_item,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": line_total,
                "pricing_type": "fixed",
            })

        else:

            amount = Decimal(
                str(
                    cart_item.get(
                        "amount",
                        "0.00",
                    )
                )
            )

            line_total = amount

            cart_items.append({
                "menu_item": menu_item,
                "quantity": 1,
                "unit_price": amount,
                "line_total": line_total,
                "pricing_type": "amount",
            })

        subtotal += line_total


    # =========================================================
    context = {
        "shop": shop,
        "cart_items": cart_items,
        "subtotal": subtotal,
    }

    return render(
        request,
        "orders/cart.html",
        context,
    )


def update_cart(request, shop_slug, menu_item_id):

    shop = get_object_or_404(
        Shop,
        slug=shop_slug,
        is_active=True,
    )

    if request.method != "POST":
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid request.",
            },
            status=400,
        )

    cart = request.session.get("cart", {})
    item_key = str(menu_item_id)

    if item_key not in cart:
        return JsonResponse(
            {
                "success": False,
                "message": "This item is no longer in your cart.",
            },
            status=404,
        )

    menu_item = get_object_or_404(
        MenuItem,
        id=menu_item_id,
        shop=shop,
        is_available=True,
    )

    if menu_item.pricing_type != "fixed":
        return JsonResponse(
            {
                "success": False,
                "message": "This item uses an amount instead of quantity.",
            },
            status=400,
        )

    try:
        quantity = int(
            request.POST.get(
                "quantity",
                "1",
            )
        )
    except (TypeError, ValueError):
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid quantity.",
            },
            status=400,
        )

    if quantity < 1:
        cart.pop(item_key, None)

        request.session["cart"] = cart
        request.session.modified = True

        cart_count = sum(
            int(item.get("quantity", 0))
            for item in cart.values()
        )

        return JsonResponse(
            {
                "success": True,
                "removed": True,
                "cart_count": cart_count,
                "line_total": "0.00",
                "subtotal": "0.00",
            }
        )

    cart[item_key]["quantity"] = quantity

    request.session["cart"] = cart
    request.session.modified = True

    unit_price = menu_item.price or Decimal("0.00")
    line_total = unit_price * quantity

    subtotal = Decimal("0.00")

    for cart_item_id, cart_item in cart.items():

        cart_menu_item = MenuItem.objects.filter(
            id=cart_item_id,
            shop=shop,
            is_available=True,
        ).first()

        if not cart_menu_item:
            continue

        cart_quantity = int(
            cart_item.get("quantity", 1)
        )

        if cart_menu_item.pricing_type == "fixed":

            cart_unit_price = (
                cart_menu_item.price or Decimal("0.00")
            )

            subtotal += (
                cart_unit_price * cart_quantity
            )

        else:

            cart_amount = Decimal(
                str(
                    cart_item.get(
                        "amount",
                        "0.00",
                    )
                )
            )

            subtotal += cart_amount

    cart_count = sum(
        int(item.get("quantity", 0))
        for item in cart.values()
    )

    return JsonResponse(
        {
            "success": True,
            "removed": False,
            "quantity": quantity,
            "line_total": f"{line_total:.2f}",
            "subtotal": f"{subtotal:.2f}",
            "cart_count": cart_count,
        }
    )

def remove_from_cart(request, shop_slug, menu_item_id):

    shop = get_object_or_404(
        Shop,
        slug=shop_slug,
        is_active=True,
    )

    if request.method != "POST":
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid request.",
            },
            status=400,
        )

    cart = request.session.get("cart", {})
    item_key = str(menu_item_id)

    if item_key not in cart:
        return JsonResponse(
            {
                "success": False,
                "message": "This item is already removed.",
            },
            status=404,
        )

    cart.pop(item_key)

    request.session["cart"] = cart
    request.session.modified = True

    cart_count = sum(
        int(item.get("quantity", 0))
        for item in cart.values()
    )

    return JsonResponse(
        {
            "success": True,
            "cart_count": cart_count,
            "removed": True,
        }
    )

def checkout(request, shop_slug):

    shop = get_object_or_404(
        Shop,
        slug=shop_slug,
        is_active=True,
    )

    cart_data = request.session.get("cart", {})
    cart_items = []
    subtotal = Decimal("0.00")

    for item_id, cart_item in cart_data.items():

        menu_item = MenuItem.objects.filter(
            id=item_id,
            shop=shop,
            is_available=True,
        ).first()

        if not menu_item:
            continue

        quantity = int(
            cart_item.get("quantity", 1)
        )

        if menu_item.pricing_type == "fixed":

            unit_price = menu_item.price or Decimal("0.00")
            line_total = unit_price * quantity

        else:

            unit_price = Decimal(
                str(
                    cart_item.get(
                        "amount",
                        "0.00",
                    )
                )
            )

            quantity = 1
            line_total = unit_price

        cart_items.append({
            "menu_item": menu_item,
            "quantity": quantity,
            "unit_price": unit_price,
            "line_total": line_total,
            "pricing_type": menu_item.pricing_type,
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
                "This shop is not configured for delivery routing yet. Please contact AirXpress.",
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
                                "Delivery unavailable at this address. "
                                "AirXpress Eats currently delivers within "
                                f"a maximum {delivery_pricing.max_radius_km} km "
                                "driving distance from this shop."
                            ),
                        )

                    else:

                        delivery_rate = (
                            DeliveryRate.objects
                            .filter(
                                delivery_pricing=delivery_pricing,
                                max_distance_km__gte=parsed_distance,
                            )
                            .order_by("max_distance_km")
                            .first()
                        )

                        if not delivery_rate:

                            messages.error(
                                request,
                                "A delivery fee could not be determined for this address.",
                            )

                        else:

                            delivery_fee = delivery_rate.delivery_fee

                            # =============================================
                            # AIRXPRESS SERVICE CHARGE
                            # 15% of the food subtotal.
                            # Backend calculation only.
                            # =============================================

                            platform_fee = (
                                subtotal * Decimal("0.15")
                            ).quantize(
                                Decimal("0.01")
                            )

                            # =============================================
                            # DRIVER PAYOUT
                            # 40% of the delivery fee.
                            # Backend calculation only.
                            # =============================================

                            driver_payout = (
                                delivery_fee * Decimal("0.40")
                            ).quantize(
                                Decimal("0.01")
                            )

                            # =============================================
                            # FINAL CUSTOMER TOTAL
                            # =============================================

                            total = (
                                subtotal
                                + delivery_fee
                                + platform_fee
                            )

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
                                        quantity=item["quantity"],
                                        unit_price=(
                                            item["unit_price"]
                                            if item["pricing_type"] == "fixed"
                                            else None
                                        ),
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

def login_gateway(request):
    return render(request, "orders/login.html")


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

            return redirect("home")

        messages.error(request, "Invalid username or password.")

    return render(request, "orders/customer_login.html")

def customer_register(request):
    from .forms import CustomerRegistrationForm

    if request.method == "POST":
        form = CustomerRegistrationForm(request.POST)

        if form.is_valid():
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

    menu_items = (
        MenuItem.objects
        .filter(
            shop=shop,
            is_available=True,
        )
        .select_related(
            "category"
        )
        .order_by(
            "category__display_order",
            "category__name",
            "display_order",
            "name",
        )
    )

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

@login_required
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

    return JsonResponse(
        {
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
            shop=shop,
            is_available=True,
        )
        .order_by(
            "name",
        )
    )

    # =========================================================
    # DRIVER VERIFICATION
    # All drivers belonging to this shop, regardless of availability.
    # =========================================================

    driver_verification_list = (
        Driver.objects
        .filter(
            shop=shop,
        )
        .order_by(
            "name",
        )
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
          "driver_verification_list": driver_verification_list,
        "driver_password_reset_list": driver_password_reset_list,
        "staff_password_reset_list": staff_password_reset_list,

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
        Driver.objects.filter(is_available=True)
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

        DeliveryRequest.objects.create(
            order=order,
            driver=driver,
            status="pending",
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

            if item.final_amount is not None:

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

                item_value = (
                    item.final_amount
                )

            else:

                item_value = (
                    item.requested_amount
                )

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

    # =========================================================
    context = {
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
def mark_driver_payout_paid(
    request,
    payout_id,
):

    if request.method != "POST":
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

        payout.status = "paid"
        payout.paid_at = timezone.now()

        payout.save(
            update_fields=[
                "status",
                "paid_at",
                "updated_at",
            ]
        )

    messages.success(
        request,
        (
            f"Driver payout for Order #{payout.order.id} "
            f"has been marked as paid."
        ),
    )

    return redirect("owner_driver_payouts")

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

    all_drivers = Driver.objects.filter(
        shop__is_active=True
    )

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
        .select_related(
            "shop"
        )
        .order_by(
            "name"
        )
    )

    # =========================================================
    # All active-shop drivers for owner password management.
    driver_password_reset_list = (
        all_drivers
        .select_related("shop", "user")
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
        shop__is_active=True,
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
# OWNER / AIRXPRESS DRIVER VERIFICATION
# =========================================================

@user_passes_test(
    is_owner,
    login_url="/owner/login/"
)
def owner_verify_driver(request, driver_id):

    if request.method != "POST":
        return redirect("owner_dashboard")

    driver = get_object_or_404(
        Driver,
        id=driver_id,
        shop__is_active=True,
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
            shop=shop,
            is_available=True,
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



