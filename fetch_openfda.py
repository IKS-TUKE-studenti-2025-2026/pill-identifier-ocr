# -*- coding: utf-8 -*-
"""
Pre každý liek v dataset/<liek>/dataset.txt:
  - načíta názov a účinné látky (SK/EN)
  - cez openFDA drug/label nájde najbližšie SPL záznamy podľa EN názvu látky
  - vytiahne sekcie: contraindications, warnings, precautions, drug_interactions, boxed_warning
  - uloží JSON: dataset/<liek>/interactions.json
  - zároveň z textu heuristicky vytiahne "choroby/stavy" (asthma, bradycardia, renal impairment, ...)

Formát dataset.txt (preferované):
  riadok 1: názov lieku
  riadok 2: účinná látka (SK)
  riadok 3: účinná látka (EN)

Ak tretí riadok chýba, použije sa riadok 2 aj ako EN.

Závislosti: requests
"""

import os
import io
import re
import json
import time
import random
import textwrap
import traceback
from pathlib import Path
from typing import Dict, List, Any

import requests
from requests.adapters import HTTPAdapter, Retry

DATASET_DIR = Path("dataset")
OUT_FILENAME = "interactions.json"

# Koľko výsledkov openFDA stiahnuť pre jednu látku (1–3 stačí)
OPENFDA_LIMIT = 2

# pauzy medzi requestami, aby sme boli gentle k API
SLEEP_BETWEEN_CALLS = (0.6, 1.3)

# Sekcie, ktoré sa pokúsime vytiahnuť z openFDA výsledkov
SECTION_KEYS = [
    "boxed_warning",
    "contraindications",
    "warnings",
    "warnings_and_cautions",
    "precautions",
    "drug_interactions",
    "adverse_reactions",
    "clinical_pharmacology",
]

# Jednoduchý slovníček „chorôb/stavov“ (stačí na MVP; rozšíriš podľa potreby)
# kľúč = kanonický názov, hodnoty = regex (alebo tuple synoným)
DISEASE_PATTERNS = {
    "asthma": r"\b(asthma|asthmatic)\b",
    "copd": r"\b(copd|chronic obstructive pulmonary disease)\b",
    "bradycardia": r"\bbradycardia\b",
    "heart block": r"\b(heart\s*block|av\s*block)\b",
    "heart failure": r"\b(heart\s*failure|cardiac\s*failure)\b",
    "ischemic heart disease": r"\b(ischemic\s+heart\s+disease|ischaemic)\b",
    "hypertension": r"\b(hypertension|high blood pressure)\b",
    "hypotension": r"\bhypotension\b",
    "arrhythmia": r"\b(arrhythmia|arrhythmias)\b",
    "diabetes": r"\b(diabetes|diabetic)\b",
    "thyroid disorders": r"\b(hyperthyroid|hypothyroid|thyroid\s+disorder)\b",
    "pheochromocytoma": r"\bpheochromocytoma\b",
    "glaucoma": r"\bglaucoma\b",
    "myasthenia gravis": r"\bmyasthenia\s+gravis\b",
    "renal impairment": r"\b(renal\s+(impairment|insufficiency|failure)|kidney\s+(failure|impairment))\b",
    "hepatic impairment": r"\b(hepatic\s+(impairment|insufficiency|failure)|liver\s+(failure|impairment))\b",
    "peptic ulcer / gi bleeding": r"\b(peptic\s+ulcer|gi\s+bleed|gastrointestinal\s+bleeding|ulceration)\b",
    "pregnancy": r"\bpregnan(cy|t)\b",
    "lactation": r"\b(lactation|breast\s*feeding|breastfeeding)\b",
    "children / pediatrics": r"\b(pediatric|children|infants)\b",
    "elderly": r"\b(elderly|geriatric|older adults?)\b",
    "seizure disorders": r"\b(seizure|epilep)\w*\b",
    "depression / suicidality": r"\b(depression|suicid)\w*\b",
}

def make_session() -> requests.Session:
    s = requests.Session()
    retries = Retry(
        total=5, connect=5, read=5,
        status_forcelist=(429, 500, 502, 503, 504),
        backoff_factor=0.8,
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (dataset-fetcher; +https://example.local)",
        "Accept": "application/json",
        "Accept-Language": "en,sk;q=0.8",
    })
    return s

SESSION = make_session()


def read_dataset_txt(path: Path) -> Dict[str, str]:
    """Načíta dataset.txt a vráti dict: name, ingredient_sk, ingredient_en"""
    with path.open("r", encoding="utf-8") as f:
        # odstránime prázdne riadky, aby sa nepomýlili indexy
        lines = [ln.strip() for ln in f if ln.strip()]
    name = lines[0] if lines else ""
    ing_sk = lines[1] if len(lines) > 1 else ""
    ing_en = lines[2] if len(lines) > 2 else (ing_sk or name)
    return {"name": name, "ingredient_sk": ing_sk, "ingredient_en": ing_en}


def openfda_fetch_sections(ingredient_en: str, limit: int = 2) -> Dict[str, Any]:
    """
    Zavolá openFDA drug/label a vytiahne sekcie textu pre danú účinnú látku (EN).
    Použijeme viac polí pre vyhľadávanie, aby to bolo tolerantnejšie.
    """
    base = "https://api.fda.gov/drug/label.json"
    # search výraz – preferuj substance_name, fallback na generic_name a active_ingredient
    queries = [
        f'openfda.substance_name:"{ingredient_en}"',
        f'openfda.generic_name:"{ingredient_en}"',
        f'active_ingredient:"{ingredient_en}"',
    ]

    collected: Dict[str, List[str]] = {k: [] for k in SECTION_KEYS}
    meta: Dict[str, Any] = {"hits": 0, "set_ids": [], "sources": []}

    for q in queries:
        try:
            r = SESSION.get(base, params={"search": q, "limit": limit, "skip": 0, "sort": "effective_time:desc"}, timeout=20)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            data = r.json()
        except Exception:
            continue

        results = data.get("results", [])
        meta["hits"] += len(results)

        for item in results:
            set_id = item.get("set_id")
            if set_id and set_id not in meta["set_ids"]:
                meta["set_ids"].append(set_id)
            # pre každú známu sekciu vyber texty (polia sú často listy stringov)
            for key in SECTION_KEYS:
                val = item.get(key)
                if isinstance(val, list):
                    collected[key].extend([v for v in val if isinstance(v, str)])
                elif isinstance(val, str):
                    collected[key].append(val)

        # krátka pauza medzi dotazmi
        time.sleep(random.uniform(*SLEEP_BETWEEN_CALLS))

        # keď už niečo máme, ďalšie queries netreba siliť
        if meta["hits"] >= 1:
            break

    # deduplikácia a zmysluplné orezanie whitespace
    for k, arr in collected.items():
        uniq = []
        seen = set()
        for t in arr:
            tnorm = " ".join(t.split())
            if tnorm and tnorm not in seen:
                seen.add(tnorm)
                # udrž rozumne dlhé (sekcie bývajú extrémne dlhé)
                uniq.append(tnorm)
        collected[k] = uniq[:5]  # max 5 odstavcov na sekciu

    return {"sections": collected, "meta": meta, "query_used": ingredient_en}


def extract_diseases_from_text(sections: Dict[str, List[str]]) -> List[str]:
    """Heuristicky nájde 'choroby/diagnózy' v textoch sekcií pomocou DISEASE_PATTERNS."""
    blob = "\n".join(
        sum([sections.get("contraindications", []),
             sections.get("warnings", []),
             sections.get("warnings_and_cautions", []),
             sections.get("precautions", []),
             sections.get("drug_interactions", [])], [])
    ).lower()

    found = []
    for canon, patt in DISEASE_PATTERNS.items():
        if re.search(patt, blob, flags=re.IGNORECASE):
            found.append(canon)
    return sorted(set(found))


def save_json(path: Path, data: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    if not DATASET_DIR.exists():
        print(f"❌ Neexistuje priečinok: {DATASET_DIR.resolve()}")
        return

    folders = [d for d in DATASET_DIR.iterdir() if d.is_dir() and (d / "dataset.txt").exists()]
    folders.sort(key=lambda p: p.name.lower())
    print(f"🎬 Spracujem {len(folders)} liekov…")

    done, nohits, errors = 0, 0, 0

    for idx, folder in enumerate(folders, 1):
        ds_path = folder / "dataset.txt"
        out_path = folder / OUT_FILENAME

        try:
            meta = read_dataset_txt(ds_path)
            name = meta["name"]
            ing_en = (meta["ingredient_en"] or meta["ingredient_sk"] or name).strip()

            if not ing_en:
                print(f"[{idx}/{len(folders)}] {folder.name}: ⚠️ chýba EN názov látky – preskakujem.")
                nohits += 1
                continue

            print(f"[{idx}/{len(folders)}] {name} — {ing_en}: ťahám openFDA…")
            res = openfda_fetch_sections(ing_en, limit=OPENFDA_LIMIT)

            sections = res.get("sections", {})
            total_len = sum(len(v) for v in sections.values())
            if total_len == 0:
                print("   ➜ Žiadne sekcie nenašli (skús iný synonym/EN názov).")
                nohits += 1
                # aj tak uložíme prázdny skeleton, nech máš konzistentnú štruktúru
                payload = {
                    "drug_name": name,
                    "ingredient_sk": meta["ingredient_sk"],
                    "ingredient_en": ing_en,
                    "source": "openfda",
                    "openfda_meta": res.get("meta", {}),
                    "sections": sections,
                    "disease_flags": [],
                }
                save_json(out_path, payload)
                continue

            diseases = extract_diseases_from_text(sections)

            payload = {
                "drug_name": name,
                "ingredient_sk": meta["ingredient_sk"],
                "ingredient_en": ing_en,
                "source": "openfda",
                "openfda_meta": res.get("meta", {}),
                "sections": sections,
                "disease_flags": diseases,  # napr. ["asthma","bradycardia","renal impairment"]
            }
            save_json(out_path, payload)
            done += 1
            print(f"   ✅ uložené → {OUT_FILENAME} (flags: {', '.join(diseases) if diseases else '—'})")

        except KeyboardInterrupt:
            print("\n⏹️ Prerušené používateľom.")
            return
        except Exception as e:
            errors += 1
            print(f"   ❌ chyba: {e}")
            traceback.print_exc()

        # slušná pauza medzi liekmi
        time.sleep(random.uniform(*SLEEP_BETWEEN_CALLS))

    print("\n🎉 Hotovo.")
    print(f"   Uložené: {done}")
    print(f"   Bez sekcií: {nohits}")
    print(f"   Chyby: {errors}")

if __name__ == "__main__":
    main()
