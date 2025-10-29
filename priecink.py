# -*- coding: utf-8 -*-
"""
build_dataset_folders.py
- Číta vstup 'vystup.txt' (striedavo: riadok s názvom lieku, ďalší riadok účinná látka)
- Pre každý pár vytvorí 'dataset/<bezpečný_názov>/' a uloží dataset.txt (1. riadok brand, 2. riadok látka)
- Rieši Windows špecifiká: zakázané znaky/názvy, koncové medzery/bodky, duplicity
- Loguje aj lexikón do dataset/_lexicon.jsonl
"""

import os
import re
import json
from pathlib import Path

INPUT_FILE = "vystup.txt"
OUTPUT_ROOT = Path("dataset")
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

# Windows zakázané názvy zariadení
RESERVED = {
    "CON","PRN","AUX","NUL",
    "COM1","COM2","COM3","COM4","COM5","COM6","COM7","COM8","COM9",
    "LPT1","LPT2","LPT3","LPT4","LPT5","LPT6","LPT7","LPT8","LPT9",
}

INVALID_CHARS = r'<>:"/\\|?*'  # + control chars vyriešime regexom
CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f]")  # ASCII control

def safe_folder_name(name: str, existing: set[str]) -> str:
    # odstráň control chars
    s = CONTROL_CHARS_RE.sub("", name)
    # vyhoď neplatné znaky
    s = "".join(c for c in s if c not in INVALID_CHARS)
    # nahrad viacnásobné medzery
    s = re.sub(r"\s{2,}", " ", s).strip()
    # odstráň koncové bodky/medzery (Windows)
    s = s.rstrip(" .")
    # ak ostalo prázdne, fallback
    if not s:
        s = "item"
    # rezervované názvy
    base = s
    if base.upper() in RESERVED:
        base = f"{base}_item"
    # obmedz dĺžku názvu (napr. 80 znakov) – zníži riziko pre MAX_PATH
    MAXLEN = 80
    if len(base) > MAXLEN:
        base = base[:MAXLEN].rstrip(" .")

    # kolízie: pridávame -2, -3, ...
    candidate = base
    n = 2
    while candidate.lower() in existing:
        trunc = base
        # nechaj priestor pre suffix "-<n>"
        if len(trunc) > MAXLEN - (len(str(n)) + 1):
            trunc = trunc[:MAXLEN - (len(str(n)) + 1)].rstrip(" .")
        candidate = f"{trunc}-{n}"
        n += 1
    existing.add(candidate.lower())
    return candidate

# --- načítanie vstupu ---
with open(INPUT_FILE, "r", encoding="utf-8") as f:
    lines = [ln.strip() for ln in f.readlines() if ln.strip()]

pairs = []
i = 0
while i < len(lines):
    brand = lines[i]
    ing = lines[i+1] if i + 1 < len(lines) else ""
    pairs.append((brand, ing))
    i += 2

# --- vytváranie priečinkov ---
existing_names = set()
lex_path = OUTPUT_ROOT / "_lexicon.jsonl"
created, skipped = 0, 0

with open(lex_path, "w", encoding="utf-8") as lex:
    for brand, ingredient in pairs:
        # bezpečný názov priečinka
        folder = safe_folder_name(brand, existing_names)
        ddir = OUTPUT_ROOT / folder

        try:
            ddir.mkdir(parents=True, exist_ok=True)
            with open(ddir / "dataset.txt", "w", encoding="utf-8") as out:
                out.write(brand.strip() + "\n")
                out.write((ingredient or "").strip() + "\n")

            # zapis do lexikonu (užitočné pre OCR postprocessing)
            lex.write(json.dumps(
                {"folder": folder, "brand": brand, "ingredient": ingredient},
                ensure_ascii=False
            ) + "\n")

            created += 1
        except Exception as e:
            print(f"❌ Nepodarilo sa vytvoriť '{folder}': {e}")
            skipped += 1

print(f"✅ Hotovo! Vytvorených: {created}, preskočených: {skipped}")
print(f"Skontroluj priečinok: {OUTPUT_ROOT}")
print(f"Lexikón: {lex_path}")
