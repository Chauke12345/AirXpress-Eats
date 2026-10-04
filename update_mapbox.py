from pathlib import Path

p = Path("orders/mapbox.py")
s = p.read_text(encoding="utf-8")

old = '''    if requested_locality:
        requested_locality_words = {
            word
            for word in requested_locality.split()
            if len(word) >= 3
        }
    else:
        requested_locality_words = set()
'''

new = '''    if requested_locality:
        requested_locality_words = {
            word
            for word in requested_locality.split()
            if len(word) >= 3
        }
    else:
        requested_locality_words = set()

    print(
        "AIRXPRESS ADDRESS CHECK:",
        "requested_locality=",
        requested_locality,
        "requested_words=",
        requested_locality_words,
    )
'''

if old not in s:
    print("TARGET NOT FOUND")
else:
    s = s.replace(old, new, 1)
    p.write_text(s, encoding="utf-8")
    print("DIAGNOSTIC ADDED")