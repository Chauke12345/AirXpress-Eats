from orders.models import MenuItem

products = [
    ("Munchie Fellas", "Chilli Cheese Kota"),
    ("Munchie Fellas", "Mushroom Tower"),
    ("Vele N'S Catering", "Grilled Chicken"),
    ("Vele N'S Catering", "Beef Stew"),
    ("EdVance Shop", "Chicken, Pap and Chakalaka"),
]

updated = 0

for shop_name, item_name in products:
    item = MenuItem.objects.filter(
        shop__name=shop_name,
        name=item_name,
        price__gt=0,
    ).first()

    if item:
        if not item.is_homepage_featured:
            item.is_homepage_featured = True
            item.save(update_fields=["is_homepage_featured"])
            updated += 1
        print("Featured:", shop_name, "|", item_name)
    else:
        print("NOT FOUND:", shop_name, "|", item_name)

print("New products marked as Popular Picks:", updated)
