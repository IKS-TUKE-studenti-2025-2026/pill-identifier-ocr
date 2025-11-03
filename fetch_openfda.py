# -*- coding: utf-8 -*-
import os, re, json, time, random, traceback
from pathlib import Path
from typing import Dict, List, Any
import requests
from requests.adapters import HTTPAdapter, Retry

DATASET_DIR = Path("dataset")
OUT_FILENAME = "interactions.json"
OPENFDA_LIMIT = 2
SLEEP_BETWEEN_CALLS = (0.6, 1.2)

SECTION_KEYS = [
    "boxed_warning","contraindications","warnings","warnings_and_cautions",
    "precautions","drug_interactions","adverse_reactions","clinical_pharmacology",
]

# jednoduché patterny na MVP „choroby/stavy“ (rozšíriš podľa potreby)
DISEASE_PATTERNS = {
    "asthma": r"\b(asthma|asthmatic)\b",
    "copd": r"\b(copd|chronic obstructive pulmonary disease)\b",
    "bradycardia": r"\bbradycardia\b",
    "heart block": r"\b(heart\s*block|av\s*block)\b",
    "heart failure": r"\b(heart\s*failure|cardiac\s*failure)\b",
    "hypertension": r"\b(hypertension|high blood pressure)\b",
    "hypotension": r"\bhypotension\b",
    "arrhythmia": r"\barrhythmia\w*\b",
    "diabetes": r"\bdiabet\w*\b",
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
    retries = Retry(total=5, connect=5, read=5,
                    status_forcelist=(429,500,502,503,504),
                    backoff_factor=0.8,
                    allowed_methods=frozenset(["GET"]),
                    raise_on_status=False)
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (openfda-fetch)",
        "Accept": "application/json",
        "Accept-Language": "en,sk;q=0.8",
    })
    return s

SESSION = make_session()

def read_dataset_txt(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    name = lines[0] if lines else ""
    ing_sk = lines[1] if len(lines) > 1 else ""
    # tretí riadok môže byť: jedno meno alebo viac mien oddelených čiarkou
    if len(lines) > 2:
        synonyms = [x.strip() for x in lines[2].split(",") if x.strip()]
    else:
        # fallback: sk použijeme ako jedno „EN“ meno
        synonyms = [ing_sk] if ing_sk else ([name] if name else [])
    return {"name": name, "ingredient_sk": ing_sk, "ingredient_en_list": synonyms}

def openfda_fetch_sections(ingredient_en: str, limit: int = 2) -> Dict[str, Any] | None:
    base = "https://api.fda.gov/drug/label.json"
    queries = [
        f'openfda.substance_name:"{ingredient_en}"',
        f'openfda.generic_name:"{ingredient_en}"',
        f'active_ingredient:"{ingredient_en}"',
    ]
    collected = {k: [] for k in SECTION_KEYS}
    meta = {"hits": 0, "set_ids": []}
    for q in queries:
        try:
            r = SESSION.get(base, params={"search": q, "limit": limit, "sort": "effective_time:desc"}, timeout=20)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            data = r.json()
        except Exception:
            continue
        results = data.get("results", [])
        meta["hits"] += len(results)
        for item in results:
            sid = item.get("set_id")
            if sid and sid not in meta["set_ids"]:
                meta["set_ids"].append(sid)
            for key in SECTION_KEYS:
                v = item.get(key)
                if isinstance(v, list):
                    collected[key] += [t for t in v if isinstance(t, str)]
                elif isinstance(v, str):
                    collected[key].append(v)
        time.sleep(random.uniform(*SLEEP_BETWEEN_CALLS))
        if meta["hits"] >= 1:
            break
    # dedupe + trim
    for k, arr in collected.items():
        seen, uniq = set(), []
        for t in arr:
            t2 = " ".join(t.split())
            if t2 and t2 not in seen:
                seen.add(t2)
                uniq.append(t2)
        collected[k] = uniq[:5]
    total = sum(len(v) for v in collected.values())
    if total == 0:
        return None
    return {"sections": collected, "meta": meta, "query_used": ingredient_en}

def extract_diseases_from_text(sections: Dict[str, List[str]]) -> List[str]:
    blob = "\n".join(
        sections.get("contraindications", []) +
        sections.get("warnings", []) +
        sections.get("warnings_and_cautions", []) +
        sections.get("precautions", []) +
        sections.get("drug_interactions", [])
    ).lower()
    found = []
    for canon, patt in DISEASE_PATTERNS.items():
        if re.search(patt, blob, flags=re.IGNORECASE):
            found.append(canon)
    return sorted(set(found))

def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    folders = [d for d in DATASET_DIR.iterdir() if d.is_dir() and (d/"dataset.txt").exists()]
    folders.sort(key=lambda p: p.name.lower())
    print(f"🎬 Spracujem {len(folders)} liekov…")

    done=nohits=errors=0
    for i, folder in enumerate(folders, 1):
        try:
            meta = read_dataset_txt(folder/"dataset.txt")
            name = meta["name"]
            en_list: List[str] = meta["ingredient_en_list"]
            tried, matched, payload = [], None, None

            print(f"[{i}/{len(folders)}] {name}: skúšam {', '.join(en_list)}")
            for candidate in en_list:
                can = candidate.strip()
                if not can: continue
                tried.append(can)
                res = openfda_fetch_sections(can, limit=OPENFDA_LIMIT)
                if res:
                    matched = can
                    sections = res["sections"]
                    diseases = extract_diseases_from_text(sections)
                    payload = {
                        "drug_name": name,
                        "ingredient_sk": meta["ingredient_sk"],
                        "ingredient_en_candidates": en_list,
                        "matched_name": matched,
                        "source": "openfda",
                        "openfda_meta": res.get("meta", {}),
                        "sections": sections,
                        "disease_flags": diseases,
                        "queries_tried": tried
                    }
                    break

            if not payload:
                nohits += 1
                payload = {
                    "drug_name": name,
                    "ingredient_sk": meta["ingredient_sk"],
                    "ingredient_en_candidates": en_list,
                    "matched_name": None,
                    "source": "openfda",
                    "openfda_meta": {},
                    "sections": {k: [] for k in SECTION_KEYS},
                    "disease_flags": [],
                    "queries_tried": tried,
                    "status": "not_found"
                }

            save_json(folder/OUT_FILENAME, payload)
            done += 1
            print(f"   ✅ uložené → {folder.name}/{OUT_FILENAME} (matched: {matched or '—'})")
            time.sleep(random.uniform(*SLEEP_BETWEEN_CALLS))

        except KeyboardInterrupt:
            print("\n⏹️ Prerušené používateľom."); return
        except Exception as e:
            errors += 1
            print(f"   ❌ chyba: {e}")
            traceback.print_exc()

    print("\n🎉 Hotovo.")
    print(f"   Uložené: {done}")
    print(f"   Bez nálezu (openFDA): {nohits}")
    print(f"   Chyby: {errors}")

if __name__ == "__main__":
    main()
