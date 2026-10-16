import json
from pathlib import Path
from django.core.serializers.json import DjangoJSONEncoder
from orders.models import Shop, Category, MenuItem

slugs = ["vele-ns-catering", "munchie-fellas"]
data = {"shops": [], "categories": [], "menu_items": []}

for shop in Shop.objects.filter(slug__in=slugs).order_by("slug"):
    data["shops"].append({
        "name": shop.name,
        "slug": shop.slug,
        "phone_number": shop.phone_number,
        "whatsapp_number": shop.whatsapp_number,
        "address": shop.address,
        "location": shop.location,
        "is_active": shop.is_active,
    })

    categories = Category.objects.filter(shop=shop).order_by("display_order", "id")
    for category in categories:
        data["categories"].append({
            "shop_slug": shop.slug,
            "name": category.name,
            "display_order": category.display_order,
            "is_active": category.is_active,
        })

    items = MenuItem.objects.filter(shop=shop).order_by("display_order", "id")
    for item in items:
        data["menu_items"].append({
            "shop_slug": shop.slug,
            "category_name": item.category.name if item.category else None,
            "name": item.name,
            "description": item.description,
            "pricing_type": item.pricing_type,
            "price": str(item.price),
            "display_order": item.display_order,
            "is_available": item.is_available,
        })

output = Path("partner_export.json")
output.write_text(json.dumps(data, indent=2, cls=DjangoJSONEncoder), encoding="utf-8")
print(f"Exported {len(data['shops'])} shops, {len(data['categories'])} categories, and {len(data['menu_items'])} menu items to {output}")
