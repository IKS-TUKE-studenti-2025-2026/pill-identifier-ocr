# -*- coding: utf-8 -*-
"""
cleanup_images.py
- Prejde všetky podpriečinky v DATASET_DIR
- ZMAŽE obrazové súbory (png, jpg, jpeg, webp, bmp, tif, tiff, jfif)
- Zachová dataset.txt a iné ne-obrázkové súbory
- Cieli hlavne na názvy: image_*.ext, color_*.jpg, *_fixed*.png, *_aug*.png
- Na konci vypíše sumár

Nastavenia:
  DRY_RUN = True  # najprv len ukáže, čo by zmazal (nezmaže)
  DELETE_CACHE = True  # zmaže aj dataset/_search_cache.json (ak existuje)
"""

import os
from pathlib import Path

DATASET_DIR = Path("dataset")

# ---- Nastavenia ----
DRY_RUN = False        # nastav na False, keď chceš reálne mazať
DELETE_CACHE = True    # zmaž aj _search_cache.json v priečinku dataset

IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".jfif"}

# Vzorové mená, ktoré chceme určite zmazať
NAME_PREFIXES = ("image_", "color_")
NAME_CONTAINS = ("_fixed", "_aug")

def is_target_image(p: Path) -> bool:
    if not p.is_file():
        return False
    if p.name.lower() == "dataset.txt":
        return False
    if p.suffix.lower() not in IMG_EXTS:
        return False
    # Preferenčne mieriť na „naše“ súbory
    n = p.name
    if n.startswith(NAME_PREFIXES) or any(tok in n for tok in NAME_CONTAINS):
        return True
    # Ale zmažeme aj iné obrázky v priečinku lieku (ak sú) – ak chceš striktne iba vyššie mená, vráť False
    return True

def main():
    if not DATASET_DIR.exists():
        print(f"❌ Neexistuje: {DATASET_DIR.resolve()}")
        return

    total, removed = 0, 0
    for folder in sorted(DATASET_DIR.iterdir()):
        if not folder.is_dir():
            continue
        # maže len v priečinkoch, ktoré vyzerajú ako „liek“ (obsahujú dataset.txt)
        if not (folder / "dataset.txt").exists():
            continue

        to_delete = [p for p in folder.iterdir() if is_target_image(p)]
        if not to_delete:
            continue

        print(f"📂 {folder.name}: {len(to_delete)} súborov na zmazanie")
        for p in to_delete:
            total += 1
            if DRY_RUN:
                print(f"  • (dry-run) {p.name}")
            else:
                try:
                    p.unlink()
                    removed += 1
                    print(f"  🗑️  {p.name}")
                except Exception as e:
                    print(f"  ⚠️  Nepodarilo sa zmazať {p.name}: {e}")

    # dataset/_search_cache.json
    cache_file = DATASET_DIR / "_search_cache.json"
    if DELETE_CACHE and cache_file.exists():
        if DRY_RUN:
            print(f"  • (dry-run) zmažem {cache_file.name}")
        else:
            try:
                cache_file.unlink()
                print(f"🗑️  Zmazané: {cache_file}")
            except Exception as e:
                print(f"⚠️  Nepodarilo sa zmazať cache: {e}")

    print("\n✅ Hotovo.")
    print(f"  Kandidátov: {total}")
    if DRY_RUN:
        print("  Režim: DRY_RUN (nič sa reálne nezmazalo). Nastav DRY_RUN=False pre ostré zmazanie.")
    else:
        print(f"  Zmazaných: {removed}")

if __name__ == "__main__":
    main()
