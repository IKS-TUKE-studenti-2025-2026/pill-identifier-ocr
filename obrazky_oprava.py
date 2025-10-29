# -*- coding: utf-8 -*-
"""
normalize_images.py
- Prejde dataset/<folder>/ s dataset.txt
- Každý obrázok normalizuje:
    * EXIF otočenie
    * grayscale (L)
    * pad/resize na 512x512 (biele pozadie)
    * mierne zvýšenie kontrastu
- Uloží ako PNG (prepíše príponu na .png) priamo do rovnakého priečinka.
- Pôvodný súbor s inou príponou po úspešnom uložení zmaže.

Bez vytvárania images/, originals/ alebo meta.jsonl.
"""

import os
import sys
from pathlib import Path
from typing import Tuple
from PIL import Image, ImageOps, ImageEnhance, ImageFile

# -------- Nastavenia --------
DATASET_DIR = Path("dataset")
TARGET_SIZE: Tuple[int, int] = (512, 512)
CONTRAST = 1.35          # 1.0 = bez zmeny
DELETE_ORIGINALS = True  # po úspešnom uložení PNG zmaž pôvodný súbor (ak mal inú príponu)
VERBOSE = True

# ak sú obrázky nekompletné, Pillow ich načíta tolerantne
ImageFile.LOAD_TRUNCATED_IMAGES = True

IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".jfif"}

def is_image_file(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in IMG_EXTS and p.name.lower() != "dataset.txt"

def normalize_one(src: Path) -> Path:
    """Načíta, normalizuje a uloží PNG vedľa zdroja (rovnaký base name). Vráti cestu k výstupu."""
    # cieľový súbor (.png) s rovnakým base menom
    dst = src.with_suffix(".png")

    # načítanie + EXIF otočenie
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        # do RGB a potom grayscale (lepší kontrast)
        im = im.convert("RGB").convert("L")
        # pad/resize na štvorcový rozmer s bielym pozadím (255)
        im = ImageOps.pad(im, TARGET_SIZE, method=Image.Resampling.LANCZOS, color=255)
        # kontrast
        if CONTRAST and CONTRAST != 1.0:
            im = ImageEnhance.Contrast(im).enhance(CONTRAST)
        # uložiť do dočasného súboru, potom atómovo nahradiť
        tmp = dst.with_suffix(".png.tmp")
        im.save(tmp, format="PNG", optimize=True)
    tmp.replace(dst)

    # ak zdroj nie je rovno .png (alebo je iný case), po úspechu zmažeme
    if DELETE_ORIGINALS and src.suffix.lower() != ".png":
        try:
            src.unlink()
        except Exception as e:
            if VERBOSE:
                print(f"   ⚠️  Nepodarilo sa zmazať pôvodný: {src.name} ({e})")
    return dst

def main():
    if not DATASET_DIR.exists():
        print(f"❌ Neexistuje priečinok: {DATASET_DIR.resolve()}")
        sys.exit(1)

    total, ok, fail = 0, 0, 0

    # prejde všetky podpriečinky, ktoré obsahujú dataset.txt
    for folder in sorted(DATASET_DIR.iterdir()):
        if not folder.is_dir():
            continue
        if not (folder / "dataset.txt").exists():
            continue

        # zoznam všetkých obrázkov (okrem dataset.txt)
        imgs = sorted(p for p in folder.iterdir() if is_image_file(p))
        if not imgs:
            if VERBOSE:
                print(f"ℹ️  {folder.name}: bez obrázkov, preskakujem.")
            continue

        if VERBOSE:
            print(f"📂 {folder.name}: {len(imgs)} súborov na normalizáciu…")

        for src in imgs:
            total += 1
            try:
                out = normalize_one(src)
                ok += 1
                if VERBOSE:
                    print(f"  ✅ {src.name} → {out.name}")
            except Exception as e:
                fail += 1
                print(f"  ❌ {src.name} – chyba: {e}")

    print("\n🎉 Hotovo.")
    print(f"   Spracovaných: {total}")
    print(f"   Úspešne:      {ok}")
    print(f"   Chýb:         {fail}")

if __name__ == "__main__":
    main()
