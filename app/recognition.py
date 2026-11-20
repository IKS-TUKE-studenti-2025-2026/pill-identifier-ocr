"""
Rozpoznanie lieku z OCR textu a fotky.

Postup: fuzzy matching -> gemma priamo z fotky (gemma z OCR textu iba ak fotka nie je k dispozícii).
Na jednej fotke môže byť viac liekov, vráti všetky nad hranicou istoty.
Odpoveď gemmy sa vždy prevedie na presný názov zo zoznamu (snap_to_list),
takže model nemôže vrátiť liek, ktorý v zozname nie je.
"""
import os
import re
import unicodedata
from fuzzywuzzy import fuzz
import llm

FUZZY_SURE = 85   # nad touto hranicou sa fuzzy výsledku verí aj bez gemmy
FUZZY_MIN = 70    # pôvodná hranica, keď gemma nič nenájde alebo nebeží
SNAP_MIN = 80     # ako veľmi sa musí odpoveď gemmy podobať názvu zo zoznamu
GEMMA_MIN = 50    # min. istota gemmy, inak sa jej odpoveď neberie (napr. náhodný obrázok)

METHOD_LABELS = {
    "fuzzy": "Fuzzy matching",
    "gemma_text": "Gemma (OCR text)",
    "gemma_vision": "Gemma (fotka)",
    "openfda": "OpenFDA",
}

# Slová, ktoré sú na mnohých krabičkách a o konkrétnom lieku nič nehovoria
# (napr. "20 tablet" sa inak zhodovalo s "MAGNEZIOVE tablety" na 85 %)
GENERIC_WORDS = {"tablety", "tablet", "tabliet", "tbl", "kapsuly", "kapsul", "kapsula", "cps",
                 "tvrde", "makke", "filmom", "obalene", "sirup", "gel", "krem", "masti", "roztok",
                 "sprej", "kvapky", "granulat", "injekcny", "tablets", "capsules"}

def clean_text(text):
    if not text: return ""
    # Odstránenie jednotiek a dávkovania pre presnejší matching
    text = re.sub(r'\d+\s*(mg|ml|g|tbl|cps|tablety|ug|%|mgml)', '', text, flags=re.IGNORECASE)
    # Diakritiku prevedieme na základné písmená, inak by z "MAGNÉZIOVÉ" ostalo "magnziov"
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    text = re.sub(r'[^a-zA-Z\s]', '', text).lower()
    return " ".join(w for w in text.split() if w not in GENERIC_WORDS)

def find_best_match(full_detected_text, pill_names_list):
    ocr_cleaned = clean_text(full_detected_text)
    if not ocr_cleaned: return None, 0
    best_match, max_score = None, 0
    for pill_name in pill_names_list:
        pill_cleaned = clean_text(pill_name)
        # partial_ratio hľadá kratší text v dlhšom. Keď je OCR text kratší ako názov lieku,
        # krátky útržok by sa "našiel" v dlhom názve, preto vtedy porovnávame celé reťazce.
        if len(ocr_cleaned) >= len(pill_cleaned):
            partial = fuzz.partial_ratio(pill_cleaned, ocr_cleaned)
        else:
            partial = fuzz.ratio(pill_cleaned, ocr_cleaned)
        score = (partial * 0.7) + (fuzz.token_set_ratio(pill_cleaned, ocr_cleaned) * 0.3)
        if score > max_score:
            max_score = score
            best_match = pill_name
    return best_match, int(max_score)

def load_pill_names(path):
    if not os.path.exists(path):
        return []
    # Za "#" môže byť poznámka (napr. odkiaľ sú dáta lieku), do názvu sa nepočíta
    with open(path, 'r', encoding='utf-8') as f:
        names = [line.split('#')[0].strip() for line in f]
    return [n for n in names if n]

def snap_to_list(name, pill_names):
    """Prevedie názov od gemmy na presný názov zo zoznamu, alebo None."""
    if not name or not isinstance(name, str):
        return None
    name = name.strip().lower()
    for pill in pill_names:
        if pill.lower() == name:
            return pill
    # Napr. "PARALEN" -> "PARALEN 500"
    scored = [((fuzz.token_set_ratio(p.lower(), name) + fuzz.ratio(p.lower(), name)) / 2, p)
              for p in pill_names]
    score, best = max(scored, default=(0, None))
    return best if score >= SNAP_MIN else None

def in_text(name, text):
    """Je názov naozaj v texte? Pri porovnaní sa ignoruje dávkovanie a interpunkcia."""
    name, text = clean_text(name), clean_text(text)
    return bool(name and text) and fuzz.partial_ratio(name, text) >= FUZZY_MIN

def accept_boxes(boxes, pill_names, ocr_text, from_photo):
    """
    Vyberie z odpovede gemmy lieky, ktorým sa dá veriť. Vráti (accepted, unknown):
      accepted - zoznam (názov zo zoznamu, istota, box)
      unknown  - boxy liekov, ktoré nie sú v zozname

    Poistka proti halucináciám: gemma občas vypíše lieky zo zoznamu, ktoré na obrázku nie sú
    (pri nich do "nazov_na_krabicke" napíše iba dávku, napr. "500 mg"). Liek preto prijmeme,
    iba ak je jeho názov v tom, čo gemma na krabičke prečítala, alebo v OCR texte.
    Pri OCR texte sa overuje iba voči OCR textu, lebo ten gemma len prepisuje.
    """
    accepted, unknown = [], []
    for box in boxes:
        score = llm.to_percent(box.get("istota"))
        if score < GEMMA_MIN:
            continue
        name = snap_to_list(box.get("liek"), pill_names)
        label = box.get("nazov_na_krabicke") or ""
        evidence = f"{label} {ocr_text}" if from_photo else ocr_text
        if not in_text(name or label, evidence):
            continue
        if name:
            accepted.append((name, score, box))
        else:
            unknown.append(box)
    return accepted, unknown

def identify_pills(ocr_blocks, image_path, pill_names, use_llm=True, use_vision=True):
    """
    Nájde všetky lieky na fotke. ocr_blocks sú odseky z EasyOCR (každý môže byť z inej krabičky).

    Vráti (pills, unknown):
      pills   - zoznam dictov {name, score, method, box} zoradený podľa istoty
      unknown - údaje od gemmy o liekoch, ktoré nie sú v zozname (pre OpenFDA)
    """
    found = {}

    def add(name, score, method, box=None):
        if name in found:
            # Rovnaký liek našli dve metódy: necháme vyššiu istotu, údaje z krabičky doplníme
            if score > found[name]["score"]:
                found[name].update(score=score, method=method)
            found[name]["box"] = found[name]["box"] or box
        else:
            found[name] = {"name": name, "score": score, "method": method, "box": box}

    # 1. Fuzzy matching na celý text aj na každý odsek zvlášť
    full_text = " ".join(ocr_blocks)
    for text in [full_text, *ocr_blocks]:
        name, score = find_best_match(text, pill_names)
        if score >= FUZZY_SURE:
            add(name, score, "fuzzy")

    llm_on = use_llm and llm.is_available()
    unknown = []

    # 2. Gemma z fotky (vráti aj údaje z krabičiek, z OCR textu ich číta nespoľahlivo)
    if llm_on and use_vision and image_path:
        boxes = llm.analyze_boxes(pill_names, image_path=image_path)
        accepted, unknown = accept_boxes(boxes, pill_names, full_text, from_photo=True)
        for name, score, box in accepted:
            add(name, score, "gemma_vision", box)

    # 3. Gemma z OCR textu, iba ak sa fotka nepoužila. Je menej presná a keď na obrázku
    #    nič nie je, často vypisuje celý zoznam liekov (trvá to aj 60 s), viď evaluate.py
    if llm_on and not (use_vision and image_path) and not found and full_text.strip():
        boxes = llm.analyze_boxes(pill_names, ocr_text=full_text)
        accepted, text_unknown = accept_boxes(boxes, pill_names, full_text, from_photo=False)
        for name, score, box in accepted:
            add(name, score, "gemma_text", box)
        unknown += text_unknown

    # 4. Pôvodná hranica fuzzy matchingu ako posledná možnosť
    if not found and not unknown:
        name, score = find_best_match(full_text, pill_names)
        if score >= FUZZY_MIN:
            add(name, score, "fuzzy")

    pills = sorted(found.values(), key=lambda p: p["score"], reverse=True)
    return pills, unknown
