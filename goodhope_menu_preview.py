from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from django.conf import settings
from orders.models import Shop, MenuItem, Category

SHOP_ID = 23
shop = Shop.objects.get(pk=SHOP_ID)
assert shop.slug == "goodhope-restaurant", f"Unexpected shop: {shop.name} / {shop.slug}"

# Preview only: this script DOES NOT create or update database records.
# Original prices are transcribed from the four Goodhope menu images.
# Selling prices = original price x 1.25, rounded to 2 decimal places.

MENU = [
    # Main meals / plates
    ("Main Meals", "Steak & Salads Only", "102.00", None),
    ("Main Meals", "Steak with Pap/Rice/Dumpling & Salads", "102.00", None),
    ("Main Meals", "Lamb Chops & Salads Only", "110.00", None),
    ("Main Meals", "Lamb Chops with Pap/Rice/Dumpling & Salads", "110.00", None),
    ("Main Meals", "Beef Stew & Salads Only", "93.00", "01_Beef_Stew.png"),
    ("Main Meals", "Beef Stew with Pap/Rice/Dumpling & Salads", "93.00", "01_Beef_Stew.png"),
    ("Main Meals", "Chicken Stew & Salads Only", "93.00", None),
    ("Main Meals", "Chicken Stew with Pap/Rice/Dumpling & Salads", "93.00", None),
    ("Main Meals", "Starch & Veges", "68.00", None),
    ("Main Meals", "Lamb Chops, Chips/Pap/Rice", "110.00", None),
    ("Main Meals", "Oxtail Stew with Salads & Rice/Pap/Dumpling", "135.00", "02_Oxtail_Stew.png"),
    ("Main Meals", "Mutton Stew with Salads & Rice/Pap/Dumpling", "115.00", "03_Mutton_Stew.png"),

    # Chicken
    ("Chicken", "Half Chicken", "75.00", "Grilled_Chicken.jpg"),
    ("Chicken", "Half Chicken with Salad Only", "95.00", "Grilled_Chicken.jpg"),
    ("Chicken", "Half Chicken with Chips & Salad", "105.00", "Grilled_Chicken.jpg"),
    ("Chicken", "Full Chicken", "140.00", "Grilled_Chicken.jpg"),
    ("Chicken", "Full Chicken with Salad Only", "160.00", "Grilled_Chicken.jpg"),
    ("Chicken", "Full Chicken with Chips & Salad", "180.00", "Grilled_Chicken.jpg"),
    ("Chicken", "4 Wings & Salad Only", "89.00", "Chicken_Wings.jpg"),
    ("Chicken", "4 Wings with Chips & Salad", "95.00", "Chicken_Wings.jpg"),
    ("Chicken", "Quarter Chicken with Chips Only", "65.00", "Quarter_Chicken.jpg"),
    ("Chicken", "Quarter Chicken with Chips & Salad", "86.00", "Quarter_Chicken.jpg"),
    ("Chicken", "Chicken Fillet with Chips", "93.00", "Chicken_Fillet.jpg"),

    # Fish and ribs
    ("Ribs & Fish", "Fish & Salad Only", "98.00", None),
    ("Ribs & Fish", "Fish & Chips", "110.00", "Fish_and_Chips.jpg"),
    ("Ribs & Fish", "Fish with Chips & Salad", "110.00", "Fish_and_Chips.jpg"),
    ("Ribs & Fish", "Pork Ribs with Salad", "120.00", "Pork_Ribs.jpg"),
    ("Ribs & Fish", "Pork Ribs with Chips & Salad", "135.00", "Pork_Ribs.jpg"),
    ("Ribs & Fish", "Beef Ribs with Salad", "110.00", "Beef_Ribs.jpg"),
    ("Ribs & Fish", "Beef Ribs with Chips & Salad", "130.00", "Beef_Ribs.jpg"),

    # Kota, Sly and specials
    ("Kota & Specials", "Kota - Polony & Special", "50.00", "Kota.jpg"),
    ("Kota & Specials", "Kota - Polony Special & Cheese", "51.00", "Kota.jpg"),
    ("Kota & Specials", "Kota - Double Cheese Only", "55.00", "Kota.jpg"),
    ("Kota & Specials", "Kota - Polony Special, Cheese & Vienna", "59.00", "Kota.jpg"),
    ("Kota & Specials", "Kota - Polony Special, Cheese & Russian", "60.00", "Kota.jpg"),
    ("Kota & Specials", "Kota - Russian", "63.00", "Kota.jpg"),
    ("Kota & Specials", "Sly - Polony & Special", "43.00", "Sly.jpg"),
    ("Kota & Specials", "Sly - Polony Special & Cheese", "47.00", "Sly.jpg"),
    ("Kota & Specials", "Sly - Double Cheese Only", "49.00", "Sly.jpg"),
    ("Kota & Specials", "Sly - Polony Special, Cheese & Vienna", "52.50", "Sly.jpg"),
    ("Kota & Specials", "Sly - Polony Special, Cheese & Russian", "53.50", "Sly.jpg"),
    ("Kota & Specials", "Sly - Russian", "57.50", "Sly.jpg"),
    ("Kota & Specials", "Grootman Special", "115.00", "Grootman_Special.jpg"),
    ("Kota & Specials", "Mince Kota", "59.00", "Kota.jpg"),
    ("Kota & Specials", "Mince Kota with Cheese", "65.00", "Kota.jpg"),

    # Chips / sides
    ("Sides & Extras", "Medium Chips", "60.00", "Chips.jpg"),
    ("Sides & Extras", "Large Chips", "63.00", "Chips.jpg"),

    # Burgers, dagwoods, wraps and toasted sandwich
    ("Burgers & Dagwoods", "Chicken Dagwood", "82.00", "Dagwood.jpg"),
    ("Burgers & Dagwoods", "Chicken Dagwood with Chips", "87.00", "Dagwood.jpg"),
    ("Burgers & Dagwoods", "Beef Dagwood", "92.00", "Dagwood.jpg"),
    ("Burgers & Dagwoods", "Beef Dagwood with Chips", "97.00", "Dagwood.jpg"),
    ("Burgers & Dagwoods", "Beef Burger", "79.00", "Beef_Burger.jpg"),
    ("Burgers & Dagwoods", "Beef Burger with Chips", "90.00", "Beef_Burger.jpg"),
    ("Wraps & Sandwiches", "Chicken Wrap", "87.00", "Chicken_Wrap.jpg"),
    ("Wraps & Sandwiches", "Chicken Wrap with Chips", "92.00", "Chicken_Wrap.jpg"),
    # The printed Beef Wrap description says "chicken strips"; leave description blank pending shop clarification.
    ("Wraps & Sandwiches", "Beef Wrap", "88.00", "Beef_Wrap.jpg"),
    ("Wraps & Sandwiches", "Beef Wrap with Chips", "93.00", "Beef_Wrap.jpg"),
    ("Wraps & Sandwiches", "Toasted Sandwich (Avocado, Cheese, Bacon, Egg, Lettuce, Tomato & Onion)", "61.00", "Toasted_Sandwich_Ham_and_Cheese.jpg"),
    ("Wraps & Sandwiches", "Toasted Sandwich with Chips", "71.00", "Toasted_Sandwich_Ham_and_Cheese.jpg"),

    # Drinks
    ("Drinks", "330ml Soft Drink", "13.00", "Cold_Drinks.jpg"),
    ("Drinks", "440ml Soft Drink", "15.00", "Cold_Drinks.jpg"),
    ("Drinks", "2L Soft Drink", "30.00", "Cold_Drinks.jpg"),
    ("Drinks", "1L Pure Juice", "45.00", "Cold_Drinks.jpg"),
    ("Drinks", "250ml Red Bull", "25.00", "Cold_Drinks.jpg"),

    # Extras (fried onion is explicitly free; retain at R0.00)
    ("Sides & Extras", "Special (Extra)", "3.00", None),
    ("Sides & Extras", "Polony (Extra)", "4.00", "Polony.jpg"),
    ("Sides & Extras", "Fried Egg (Extra)", "5.00", "Fried_Egg.jpg"),
    ("Sides & Extras", "Cheese (Extra)", "6.00", "Cheese.jpg"),
    ("Sides & Extras", "Avocado (Extra)", "9.00", "Avocado.jpg"),
    ("Sides & Extras", "Vienna (Extra)", "9.00", "Vienna.jpg"),
    ("Sides & Extras", "Russian (Extra)", "16.00", "Russian.jpg"),
    ("Sides & Extras", "Loaf of Bread", "23.00", None),
    ("Sides & Extras", "Bacon (Extra)", "16.00", "Bacon.jpg"),
    ("Sides & Extras", "Fried Onion (Extra)", "0.00", None),
    ("Sides & Extras", "Beef Patty (Extra)", "18.00", None),
    ("Sides & Extras", "1 Slice of Bread", "1.50", None),
    ("Sides & Extras", "2 Toasted Slices", "5.00", None),
    ("Sides & Extras", "1 Spoon of Atchar", "6.00", None),
    ("Sides & Extras", "Lettuce & Tomato", "4.00", None),
    ("Sides & Extras", "Dumpling", "15.00", "Dumpling.jpg"),
    ("Sides & Extras", "Pap", "15.00", "Pap.jpg"),
    ("Sides & Extras", "Rice", "15.00", "Rice.jpg"),
]

media_root = Path(settings.MEDIA_ROOT)
image_dir = media_root / "menu_items" / "goodhope"
existing_names = set(MenuItem.objects.filter(shop_id=SHOP_ID).values_list("name", flat=True))

print("\nGOODHOPE MENU PREVIEW — NO DATABASE CHANGES")
print("Shop:", shop.name, "| ID:", shop.pk, "| slug:", shop.slug)
print("Existing Goodhope menu items:", MenuItem.objects.filter(shop_id=SHOP_ID).count())
print("Existing Goodhope categories:", Category.objects.filter(shop_id=SHOP_ID).count())
print("Proposed categories:", ", ".join(dict.fromkeys(row[0] for row in MENU)))
print("Proposed menu item count:", len(MENU))
print("\n{:<4} {:<25} {:<67} {:>10} {:>12}  {}".format("No.", "CATEGORY", "ITEM", "ORIGINAL", "SELLING", "IMAGE"))
print("-" * 150)

missing_images = []
for i, (category, name, original, image_name) in enumerate(MENU, 1):
    original_price = Decimal(original)
    selling_price = (original_price * Decimal("1.25")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    image_status = "-"
    if image_name:
        exists = (image_dir / image_name).is_file()
        image_status = image_name + (" [OK]" if exists else " [MISSING]")
        if not exists:
            missing_images.append(image_name)
    duplicate = " [NAME EXISTS]" if name in existing_names else ""
    print("{:<4} {:<25} {:<67} R{:>9} R{:>11}  {}{}".format(i, category, name[:67], original_price, selling_price, image_status, duplicate))

print("\nSUMMARY")
print("Items in preview:", len(MENU))
print("Unique categories:", len(set(row[0] for row in MENU)))
print("Missing referenced image files:", sorted(set(missing_images)) or "None")
print("Existing item-name collisions:", sorted(set(row[1] for row in MENU) & existing_names) or "None")
print("\nPREVIEW ONLY: no Category or MenuItem records were created or changed.")
