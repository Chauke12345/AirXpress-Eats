import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

exec(compile(
    open("register_prelaunch_shops.py", encoding="utf-8-sig").read(),
    "register_prelaunch_shops.py",
    "exec"
))
