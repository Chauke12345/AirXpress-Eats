from orders.models import MenuItem

def suggest(item):
    name = item.name.lower()
    category = item.category.name.lower() if item.category else ""
    text = name + " " + category

    if any(x in text for x in ["soft drink", "water", "juice", "drink", "beverage"]):
        return "drinks"
    if any(x in text for x in ["chicken, pap", "pork chop, pap", "steak, pap", "wors, pap", "wings & chips"]):
        return "main_meals"
    if any(x in text for x in ["chakalaka", "coleslaw", "pap", "potato salad", "fries", "chips"]):
        return "sides"
    if any(x in text for x in ["burger", "kota"]):
        return "burgers"
    if "ribs and wings" in name:
        return "main_meals"
    if any(x in text for x in ["chicken", "wings"]):
        return "chicken"
    if any(x in text for x in ["boerewors", "wors", "steak", "ribs", "pork chop", "meat selection"]):
        return "meat_braai"
    if any(x in text for x in ["dessert", "cake", "ice cream"]):
        return "desserts"
    if any(x in text for x in ["main meals", "combos", "beef stew", "hake", "calamari", "curry", "mushroom tower"]):
        return "main_meals"
    return ""

updated = 0
skipped = 0

for item in MenuItem.objects.select_related("category").filter(homepage_category=""):
    category = suggest(item)
    if category:
        item.homepage_category = category
        item.save(update_fields=["homepage_category"])
        updated += 1
    else:
        skipped += 1

print("Products assigned:", updated)
print("Products left for review:", skipped)
