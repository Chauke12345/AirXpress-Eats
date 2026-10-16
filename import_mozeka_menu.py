from pathlib import Path
from shutil import copy2

from django.conf import settings
from django.db import transaction

from orders.models import Shop, Category, MenuItem

SHOP_ID = 20
SHOP_NAME = "Mozeka & Sons Catering Services"
SOURCE_DIR = Path(settings.MEDIA_ROOT) / "drivers" / "Mozeka & Sons images"
DEST_DIR = Path(settings.MEDIA_ROOT) / "menu_items"
CATEGORY_NAME = "Main Meals"

MENU = [
    ("IMG-20261015-WA0005.jpg", "Grilled Meat Platter with Rice and Vegetables", "Grilled meat served with rice and vegetables."),
    ("IMG-20261015-WA0006.jpg", "Mixed Meat Stew with Yellow Rice and Sides", "Mixed meat stew served with yellow rice and side dishes."),
    ("IMG-20261015-WA0007.jpg", "Grilled Chicken with Rice and Salad", "Grilled chicken served with rice and salad."),
    ("IMG-20261015-WA0008.jpg", "Spicy Chicken Feet with Steamed Bread", "Spicy chicken feet served with steamed bread."),
    ("IMG-20261015-WA0009_edit_172188176439001.jpg", "Assorted Traditional Meat Platter", "A platter of assorted traditional meats."),
    ("IMG-20261015-WA0010.jpg", "Chicken, Rice, Stew and Salad Platter", "Chicken served with rice, stew and salad."),
    ("IMG-20261015-WA0011.jpg", "Prawn Platter with Rice", "Prawns served with rice."),
    ("IMG-20261015-WA0013.jpg", "Traditional Meat and Chicken Feet Platter", "Traditional meat and chicken feet served together."),
    ("IMG-20261015-WA0014.jpg", "Braised Trotters with Rice and Vegetables", "Braised trotters served with rice and vegetables."),
    ("IMG-20261015-WA0015.jpg", "Chicken Feet and Assorted Meat Platter", "Chicken feet served with assorted meats."),
    ("IMG-20261015-WA0016(1).jpg", "Seafood Platter with Pasta and Vegetables", "Seafood served with pasta and vegetables."),
    ("IMG-20261015-WA0017.jpg", "Beef Stew with Dumplings and Vegetables", "Beef stew served with dumplings and vegetables."),
    ("IMG-20261015-WA0039.jpg", "Grilled Fish with Pap and Salad", "Grilled fish served with pap and salad."),
    ("IMG-20261015-WA0040.jpg", "Grilled Lamb Chops with Pap and Sides", "Grilled lamb chops served with pap and side dishes."),
    ("IMG-20261015-WA0041.jpg", "Grilled Chicken with Pap, Salad and Sides", "Grilled chicken served with pap, salad and side dishes."),
    ("IMG-20261015-WA0042.jpg", "Chicken Meal with Salad and Sides", "Chicken served with salad and side dishes."),
]

def main():
    shop = Shop.objects.filter(pk=SHOP_ID, name=SHOP_NAME).first()
    if shop is None:
        raise RuntimeError("STOP: the expected shop was not found.")

    if MenuItem.objects.filter(shop=shop).exists():
        raise RuntimeError("STOP: this shop already has menu items. Nothing imported.")

    if Category.objects.filter(shop=shop, name=CATEGORY_NAME).exists():
        raise RuntimeError("STOP: the target category already exists. Review before importing.")

    missing = [filename for filename, _, _ in MENU if not (SOURCE_DIR / filename).is_file()]
    if missing:
        raise RuntimeError(f"STOP: missing source files: {missing}")

    DEST_DIR.mkdir(parents=True, exist_ok=True)

    # Avoid overwriting any existing media files.
    destination_names = [filename for filename, _, _ in MENU]
    collisions = [name for name in destination_names if (DEST_DIR / name).exists()]
    if collisions:
        raise RuntimeError(f"STOP: destination images already exist: {collisions}")

    created_count = 0
    copied_files = []

    try:
        with transaction.atomic():
            category = Category.objects.create(
                shop=shop,
                name=CATEGORY_NAME,
                display_order=0,
                is_active=True,
            )

            for index, (filename, name, description) in enumerate(MENU, start=1):
                source = SOURCE_DIR / filename
                destination = DEST_DIR / filename
                copy2(source, destination)
                copied_files.append(destination)

                MenuItem.objects.create(
                    shop=shop,
                    category=category,
                    name=name,
                    description=description,
                    pricing_type="fixed",
                    price=None,
                    image=f"menu_items/{filename}",
                    display_order=index,
                    is_available=False,
                    is_homepage_featured=False,
                )
                created_count += 1

    except Exception:
        for path in copied_files:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise

    print(f"SUCCESS: created {created_count} menu items for {shop.name} (ID {shop.pk}).")
    print(f"Category: {category.name} (ID {category.pk})")
    print(f"Images copied to: {DEST_DIR}")
    print("All prices are blank and all items are unavailable.")
    print("Original source photographs were not moved or deleted.")

if __name__ == "__main__":
    main()
