
from decimal import Decimal
from django.db import transaction
from orders.models import Shop, MenuItem, OrderItem

SHOP_ID = 20
CATEGORY_ID = 10

dishes = [
    ("Thursday - Grilled Chicken", "110.00", "Thursday menu. Starch: Savoury Rice (Basmati) or Pap. Three sides available."),
    ("Thursday - Lamb Chops", "160.00", "Thursday menu. Starch: Savoury Rice (Basmati) or Pap. Three sides available."),
    ("Thursday - T-Bone Steak", "130.00", "Thursday menu. Starch: Savoury Rice (Basmati) or Pap. Three sides available."),
    ("Thursday - Short Rib Stew", "130.00", "Thursday menu. Starch: Savoury Rice (Basmati) or Pap. Three sides available."),
    ("Friday - Grilled Fish", "120.00", "Friday menu. Starch: Savoury Rice (Basmati) or Fries / Potato Wedges."),
    ("Friday - Salmon", "190.00", "Friday menu. Starch: Savoury Rice (Basmati) or Fries / Potato Wedges."),
    ("Friday - Seafood Basket", "140.00", "Friday menu. Starch: Savoury Rice (Basmati) or Fries / Potato Wedges."),
    ("Friday - Butter Chicken", "110.00", "Friday menu. Starch: Savoury Rice (Basmati) or Fries / Potato Wedges."),
    ("Friday - T-Bone Steak", "130.00", "Friday menu. Starch: Savoury Rice (Basmati) or Fries / Potato Wedges."),
    ("Friday - Seafood Boil (Pre-order)", "380.00", "Friday menu. Pre-order required. Starch: Savoury Rice (Basmati) or Fries / Potato Wedges."),
    ("Saturday - T-Bone Steak", "130.00", "Saturday menu. Starch: Savoury Rice (Basmati), Pap + Fries. Three sides available."),
    ("Saturday - Lamb Chops", "160.00", "Saturday menu. Starch: Savoury Rice (Basmati), Pap + Fries. Three sides available."),
    ("Saturday - Mix Grill (Wors, Chicken, Steak)", "230.00", "Saturday menu. Starch: Savoury Rice (Basmati), Pap + Fries. Three sides available."),
    ("Saturday - Grilled Chicken", "110.00", "Saturday menu. Starch: Savoury Rice (Basmati), Pap + Fries. Three sides available."),
    ("Sunday Lunch - Lamb Shank (Pre-order)", "230.00", "Sunday lunch. Pre-order required. Starch: Savoury Rice (Basmati), Dumpling or Creamy Mash Potato."),
    ("Sunday Lunch - Short Rib Stew", "130.00", "Sunday lunch. Starch: Savoury Rice (Basmati), Dumpling or Creamy Mash Potato."),
    ("Sunday Lunch - Grilled Fish", "120.00", "Sunday lunch. Starch: Savoury Rice (Basmati), Dumpling or Creamy Mash Potato."),
    ("Sunday Lunch - T-Bone Steak", "130.00", "Sunday lunch. Starch: Savoury Rice (Basmati), Dumpling or Creamy Mash Potato."),
    ("Monday - African Cuisine - Mogodu", "110.00", "Monday African cuisine. Starch: Ting, Samp or Dumpling. Three sides available."),
    ("Monday - African Cuisine - Hardbody Chicken", "120.00", "Monday African cuisine. Starch: Ting, Samp or Dumpling. Three sides available."),
    ("Monday - African Cuisine - Pork Trotters", "100.00", "Monday African cuisine. Starch: Ting, Samp or Dumpling. Three sides available."),
    ("Monday - African Cuisine - Malana", "90.00", "Monday African cuisine. Starch: Ting, Samp or Dumpling. Three sides available."),
    ("Monday - African Cuisine - Gizzards", "80.00", "Monday African cuisine. Starch: Ting, Samp or Dumpling. Three sides available."),
    ("Monday - African Cuisine - Chicken Feet", "80.00", "Monday African cuisine. Starch: Ting, Samp or Dumpling. Three sides available."),
]

shop = Shop.objects.get(pk=SHOP_ID)

if shop.name != "Mozeka & Sons Catering Services":
    raise Exception("Stopped: shop name did not match.")

if OrderItem.objects.filter(menu_item__shop=shop).exists():
    raise Exception("Stopped: existing order items were found. No menu changes made.")

if not MenuItem.objects.filter(shop=shop, category_id=CATEGORY_ID).exists():
    raise Exception("Stopped: expected menu category was not found.")

with transaction.atomic():
    existing = list(
        MenuItem.objects.filter(shop=shop).order_by("display_order", "id")
    )

    if len(existing) != 16:
        raise Exception(
            f"Stopped: expected 16 existing items, found {len(existing)}."
        )

    for index, (name, base_price, description) in enumerate(dishes, start=1):
        if index <= len(existing):
            item = existing[index - 1]
            item.name = name
            item.description = description
            item.pricing_type = "fixed"
            item.price = Decimal(base_price)
            item.display_order = index
            item.is_available = True
            item.save()
        else:
            MenuItem.objects.create(
                shop=shop,
                category_id=CATEGORY_ID,
                name=name,
                description=description,
                pricing_type="fixed",
                price=Decimal(base_price),
                display_order=index,
                is_available=True,
            )

print("MENU UPDATE COMPLETED")
print("Shop:", shop.name)
print("Available dishes:", MenuItem.objects.filter(shop=shop, is_available=True).count())
