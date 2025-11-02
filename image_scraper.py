# -*- coding: utf-8 -*-
"""
reconcile_vystup_with_folders.py

- Číta vstupný TXT (vystup.txt) po dvojiciach riadkov:
    1) názov lieku
    2) účinná látka
- Overí, že v dataset/<safe_name> existuje priečinok (safe_name = názov bez zakázaných znakov Windows).
- Ak priečinok NEexistuje, dvojicu z TXT odstráni.
- Zapíše späť do toho istého súboru, ale najprv vytvorí zálohu.

Záloha: vystup.backup-YYYYmmdd-HHMMSS.txt
Formát výstupu: každý liek + jeho látka na dvoch riadkoch, medzi pármi prázdny riadok.
"""

import os
import shutil
from datetime import datetime
from pathlib import Path

DATASET_DIR = Path("dataset")
INPUT_TXT   = Path("vystup.txt")

# nastav, ak chceš len ukázať, čo by sa zmenilo (bez zápisu)
DRY_RUN = False

def safe_name(name: str) -> str:
    # rovnaká sanitácia ako si mal pri vytváraní priečinkov
    forbidden = '<>:"/\\|?*'
    return "".join(c for c in name if c not in forbidden)

def read_pairs(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Neexistuje: {path}")
    with path.open("r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    pairs = []
    for i in range(0, len(lines), 2):
        if i + 1 < len(lines):
            pairs.append( (lines[i], lines[i+1]) )
    return pairs

def write_pairs(path: Path, pairs):
    with path.open("w", encoding="utf-8") as out:
        for i, (name, ing) in enumerate(pairs):
            out.write(name.rstrip() + "\n")
            out.write(ing.rstrip() + "\n")
            if i != len(pairs) - 1:
                out.write("\n")

def main():
    if not DATASET_DIR.exists():
        print(f"❌ Neexistuje priečinok: {DATASET_DIR.resolve()}")
        return
    pairs = read_pairs(INPUT_TXT)
    if not pairs:
        print("⚠️  vstup je prázdny alebo nemá platné dvojice.")
        return

    # pre rýchle case-insensitive porovnanie priprav zoznam existujúcich priečinkov
    existing_dirs = {p.name.lower(): p for p in DATASET_DIR.iterdir() if p.is_dir()}

    kept, removed = [], []
    for (name, ing) in pairs:
        s = safe_name(name).strip()
        # porovnávaj case-insensitive
        exists = (s.lower() in existing_dirs)
        if exists:
            kept.append((name, ing))
        else:
            removed.append((name, ing))

    print(f"🔎 Našiel som {len(pairs)} položiek v TXT.")
    print(f"   ✔️  ponechané: {len(kept)}")
    print(f"   🗑️  vyhodené:  {len(removed)}")

    if removed:
        print("\n🗒️  Zoznam chýbajúcich (nemajú priečinok v dataset/):")
        for name, ing in removed[:20]:
            print(f"  - {name}")
        if len(removed) > 20:
            print(f"  … a ďalších {len(removed) - 20} položiek")

    if DRY_RUN:
        print("\n(DRY_RUN=True) – súbor som NEupravil. Nastav DRY_RUN=False pre zápis.")
        return

    # záloha
    backup = INPUT_TXT.with_name(f"vystup.backup-{datetime.now():%Y%m%d-%H%M%S}.txt")
    shutil.copy2(INPUT_TXT, backup)
    print(f"\n🛟 Záloha uložená do: {backup.name}")

    # zápis filtrovaného zoznamu
    write_pairs(INPUT_TXT, kept)
    print(f"✅ Hotovo. Prepísaný súbor: {INPUT_TXT.name}")

if __name__ == "__main__":
    main()
