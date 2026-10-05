from pathlib import Path
from django.core.files import File
from orders.models import MenuItem

BASE = Path.cwd() / "airxpress_generated_menu_images"

for entry in [
    ("Beef Steak", "beef_steak"),
    ("Boerewors", "boerewors"),
    ("Chicken Pieces", "chicken_pieces"),
    ("Pork Chops", "pork_chops"),
    ("Beef Short Ribs", "beef_short_ribs"),
    ("Wors, Pap and Chakalaka", "wors__pap_and_chakalaka"),
    ("Chicken, Pap and Chakalaka", "chicken__pap_and_chakalaka"),
    ("Steak, Pap and Chakalaka", "steak__pap_and_chakalaka"),
    ("Pork Chop, Pap and Chakalaka", "pork_chop__pap_and_chakalaka"),
    ("Pap", "pap"),
    ("Chakalaka", "chakalaka"),
    ("Coleslaw", "coleslaw"),
    ("Potato Salad", "potato_salad"),
    ("Soft Drink 330ml", "soft_drink_330ml"),
    ("Soft Drink 500ml", "soft_drink_500ml"),
    ("Soft Drink 2L", "soft_drink_2l"),
    ("Still Water", "still_water"),
    ("Demo Beef Steak", "demo_beef_steak"),
    ("Demo Boerewors", "demo_boerewors"),
    ("Demo Chakalaka", "demo_chakalaka"),
    ("Demo Pap", "demo_pap"),
    ("Demo Soft Drink", "demo_soft_drink"),
    ("Demo Water", "demo_water"),
]:
    menu_name, filename = entry
    item = MenuItem.objects.filter(name=menu_name).first()
    image_path = BASE / f"{filename}.jpg"

    if not item:
        print(f"SKIP - menu item not found: {menu_name}")
        continue

    if not image_path.exists():
        print(f"SKIP - image missing: {image_path}")
        continue

    with image_path.open("rb") as f:
        item.image.save(image_path.name, File(f), save=True)

    print(f"ATTACHED - {menu_name} -> {image_path.name}")

print("DONE - generated menu images attached where matching menu items exist.")