import os
import json
from pathlib import Path

DATASET_DIR = Path("dataset")

not_found = []
found = 0

for folder in sorted(DATASET_DIR.iterdir()):
    if not folder.is_dir():
        continue
    fpath = folder / "interactions.json"
    if not fpath.exists():
        continue
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("status") == "not_found" or not any(data.get("sections", {}).values()):
            not_found.append(folder.name)
        else:
            found += 1
    except Exception as e:
        print(f"⚠️ Chyba pri čítaní {folder.name}: {e}")

print("\n=== 🧠 PREHĽAD ===")
print(f"Nájdené údaje pre: {found}")
print(f"Nenájdené: {len(not_found)}\n")

if not_found:
    print("❌ Chýbajúce látky:")
    for name in not_found:
        print(" -", name)
else:
    print("✅ Všetky lieky majú údaje.")
