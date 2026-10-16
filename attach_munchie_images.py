from pathlib import Path
from django.core.files import File
from orders.models import Shop, MenuItem

shop = Shop.objects.get(slug="munchie-fellas")
image_dir = Path("static/orders/images/munchie_fellas_food_images")

image_map = {
    "Americano": "americano.jpg",
    "Weekend Special": "weekend-special.jpg",
    "Mushroom Tower": "mushroom-tower.jpg",
    "Kota Begar": "kota-begar.jpg",
    "Chilli Cheese Kota": "chilli-cheese-kota.jpg",
    "Ghost Chilli Cheese Fries": "ghost-chilli-cheese-fries.jpg",
}

for name, filename in image_map.items():
    path = image_dir / filename
    if not path.is_file():
        print(f"MISSING: {path}")
        continue
    item = MenuItem.objects.get(shop=shop, name=name)
    with path.open("rb") as f:
        item.image.save(filename, File(f), save=True)
    print(f"ATTACHED: {name}")

print("IMAGE ATTACHMENT FINISHED")
