from pathlib import Path
from django.utils.text import slugify
from orders.models import Shop

logo_dir = Path("media/shop_logos")
shops = [
    ("The Love of Alex", "1000775303(1).jpg", "16th Avenue, Alexandra, Johannesburg, 2090"),
    ("Mike's Food Restaurant", "1000775304(1).jpg", ""),
    ("Bev's Kitchen", "1000775305(1).jpg", ""),
    ("Naledi's Slay & Takeaway", "1000775306(1).jpg", "23 5th Avenue Joe Nhlanhla Road Alexandra, Alexandra, Johannesburg, 2090"),
    ("KO2ND Pub N Restaurant", "1000775307(1).jpg", "6139 2nd Ave, Alexandra, Johannesburg, 2090"),
    ("Lady G's Kitchen", "1000775310(1).jpg", ""),
    ("Porangi World", "1000775311(1).jpg", "3145 Far East Bank St, Far East Bank, Alexandra, 20142"),
    ("Sioa Culinary", "1000775312(1).jpg", "384 E Bank Ave, East Bank, Alexandra, 2014"),
    ("New Food Joint", "1000775313(1).jpg", ""),
    ("Baily's", "1000775314.jpg", ""),
    ("Ka Djyong", "1000775315.jpg", ""),
    ("Masuku Inc. Catering Services", "1000775316.jpg", ""),
    ("LUMOS Coffee Cafe", "1000775317(1).jpg", "5974 Richard Baloyi St, Alexandra, Johannesburg, 2014"),
    ("Taste of Ducci", "1000775318(1).jpg", ""),
    ("AZO's Kitchen", "1000775319(1).jpg", ""),
    ("Mozeka & Sons Catering Services", "1000775320(1).jpg", "126 Phase One, 8th Avenue Alexandra, Sandton, 2090"),
    ("T&K Fast Food", "1000775321(1).jpg", "519 10th Rd, Liberia tsutsumane, Alexandra, 2090"),
    ("NTIMAS African Cuisine", "1000775322(1).jpg", "Stoep 15, 123 15th Ave, Alexandra, 2014"),
    ("Goodhope Restaurant", "1000775323.jpg", "2008 10th Ave, Alexandra, 2014"),
]

missing = [f for _, f, _ in shops if not (logo_dir / f).is_file()]
if missing:
    print("STOPPED - missing logos:", missing)
else:
    created = 0
    skipped = 0
    for name, filename, address in shops:
        slug = slugify(name)
        existing = Shop.objects.filter(slug=slug).first()
        if existing:
            print(f"SKIPPED: {existing.name} already exists")
            skipped += 1
            continue

        shop = Shop(
            name=name,
            slug=slug,
            phone_number="",
            whatsapp_number="",
            address=address,
            location="Alexandra, Johannesburg" if address else "",
            is_active=True,
            banking_status="pending",
        )
        shop.logo.name = f"shop_logos/{filename}"
        shop.save()
        print(f"CREATED: {shop.name}")
        created += 1

    print(f"DONE: {created} created; {skipped} skipped.")
