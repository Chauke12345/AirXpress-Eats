from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from django.conf import settings
from django.db import transaction
from orders.models import Shop, MenuItem, Category

# Reuse the exact approved menu data.
from goodhope_menu_preview import MENU

SHOP_ID = 23
shop = Shop.objects.get(pk=SHOP_ID)

# Safety checks: only Goodhope may be changed.
if shop.slug != "goodhope-restaurant":
    raise Exception("STOP: Shop identity does not match Goodhope.")

if MenuItem.objects.filter(shop_id=SHOP_ID).exists():
    raise Exception("STOP: Goodhope already has menu items.")

if Category.objects.filter(shop_id=SHOP_ID).exists():
    raise Exception("STOP: Goodhope already has categories.")

if MenuItem.objects.filter(shop_id=SHOP_ID).count() != 0:
    raise Exception("STOP: Existing menu items detected.")

image_dir = Path(settings.MEDIA_ROOT) / "menu_items" / "goodhope"

missing = sorted({
    image_name
    for _, _, _, image_name in MENU
    if image_name and not (image_dir / image_name).is_file()
})

if missing:
    raise Exception(f"STOP: Missing images: {missing}")

category_names = list(dict.fromkeys(row[0] for row in MENU))

print("\nGOODHOPE IMPORT CHECK")
print("Shop:", shop.name, "| ID:", shop.pk)
print("Categories:", len(category_names))
print("Menu items:", len(MENU))
print("Missing images: 0")
print("Markup: 25%")
print("\nNothing has been imported yet.")

confirmation = input(
    "\nType IMPORT GOODHOPE to create these records: "
).strip()

if confirmation != "IMPORT GOODHOPE":
    print("Import cancelled. No database changes made.")
else:
    with transaction.atomic():
        # Recheck inside the transaction.
        if MenuItem.objects.filter(shop_id=SHOP_ID).exists():
            raise Exception("STOP: Menu items appeared before import.")

        if Category.objects.filter(shop_id=SHOP_ID).exists():
            raise Exception("STOP: Categories appeared before import.")

        categories = {}

        for position, category_name in enumerate(category_names, start=1):
            categories[category_name] = Category.objects.create(
                shop=shop,
                name=category_name,
                display_order=position,
                is_active=True,
            )

        for position, (category_name, name, original, image_name) in enumerate(MENU, start=1):
            original_price = Decimal(original)
            selling_price = (
                original_price * (Decimal("1.10") if category_name == "Drinks" else Decimal("1.25"))
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            item = MenuItem(
                shop=shop,
                category=categories[category_name],
                name=name,
                description="",
                pricing_type="fixed",
                price=selling_price,
                display_order=position,
                is_available=True,
            )

            if image_name:
                item.image = f"menu_items/goodhope/{image_name}"

            item.save()

    print("\nIMPORT COMPLETED")
    print("Shop:", shop.name, "| ID:", shop.pk)
    print("Categories created:", Category.objects.filter(shop_id=SHOP_ID).count())
    print("Menu items created:", MenuItem.objects.filter(shop_id=SHOP_ID).count())
