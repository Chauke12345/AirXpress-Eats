
from decimal import Decimal
from django.db import transaction
from orders.models import Shop, Category, MenuItem

with transaction.atomic():
    shop = Shop.objects.select_for_update().get(pk=15)

    if shop.slug not in ("ka-djyong", "ko-djyong"):
        raise RuntimeError(
            f"Unexpected slug for Shop 15: {shop.slug}. Nothing changed."
        )

    if Shop.objects.exclude(pk=15).filter(slug="ko-djyong").exists():
        raise RuntimeError(
            "Another shop already uses the ko-djyong slug. Nothing changed."
        )

    if MenuItem.objects.filter(shop=shop).exists():
        raise RuntimeError(
            "Shop 15 already has menu items. Stop to avoid overwriting them."
        )

    shop.name = "Ko Dijong"
    shop.slug = "ko-djyong"
    shop.save()

    main_meals, _ = Category.objects.get_or_create(
        shop=shop,
        name="Main Meals",
        defaults={"display_order": 1, "is_active": True},
    )
    extras_category, _ = Category.objects.get_or_create(
        shop=shop,
        name="Extras",
        defaults={"display_order": 2, "is_active": True},
    )

    menu_items = [
        {
            "category": main_meals,
            "name": "Chicken – Pap / Samp",
            "description": "Chicken served with pap or samp.",
            "price": Decimal("80.00"),
            "display_order": 1,
            "is_available": True,
            "image": "menu_items/chicken_pap_samp.jpg",
        },
        {
            "category": main_meals,
            "name": "Meaty Bones – Pap",
            "description": "Meaty bones served with pap.",
            "price": Decimal("75.00"),
            "display_order": 2,
            "is_available": True,
            "image": "menu_items/meaty_bones_pap.jpg",
        },
        {
            "category": main_meals,
            "name": "Inhloko – Pap",
            "description": "Inhloko served with pap.",
            "price": Decimal("80.00"),
            "display_order": 3,
            "is_available": True,
            "image": "menu_items/inhloko_pap.jpg",
        },
        {
            "category": main_meals,
            "name": "Mogodu – Pap",
            "description": "Price to be confirmed. Currently unavailable.",
            "price": None,
            "display_order": 4,
            "is_available": False,
            "image": "menu_items/mogodu_pap.jpg",
        },
        {
            "category": extras_category,
            "name": "Cow Heels",
            "description": "Optional extra.",
            "price": Decimal("20.00"),
            "display_order": 1,
            "is_available": True,
            "image": "menu_items/cow_heels.jpg",
        },
        {
            "category": extras_category,
            "name": "Samp Only",
            "description": "Optional extra.",
            "price": Decimal("30.00"),
            "display_order": 2,
            "is_available": True,
            "image": "menu_items/samp_only.jpg",
        },
        {
            "category": extras_category,
            "name": "Pap Only",
            "description": "Optional extra.",
            "price": Decimal("15.00"),
            "display_order": 3,
            "is_available": True,
            "image": "menu_items/pap_only.jpg",
        },
    ]

    for item in menu_items:
        MenuItem.objects.create(
            shop=shop,
            category=item["category"],
            name=item["name"],
            description=item["description"],
            pricing_type="fixed",
            price=item["price"],
            display_order=item["display_order"],
            is_available=item["is_available"],
            image=item["image"],
        )

    print("Shop updated:", shop.pk, shop.name, shop.slug)
    print("Menu created:", MenuItem.objects.filter(shop=shop).count())
