from datetime import date
from orders.models import MenuItem

items = list(
    MenuItem.objects.filter(
        shop__is_active=True,
        is_available=True,
        price__gt=0,
    ).exclude(
        homepage_category=""
    ).select_related(
        "shop"
    ).order_by("pk")
)

if items:
    anchor = date(2024, 1, 1)
    week_index = (date.today() - anchor).days // 7
    start = week_index % len(items)
    rotated = items[start:] + items[:start]
    selected = rotated[:5]

    print("Eligible products:", len(items))
    print("Selected Popular Picks:", len(selected))
    for item in selected:
        print(item.shop.name, "|", item.name, "| R", item.price)
else:
    print("No eligible products found.")
