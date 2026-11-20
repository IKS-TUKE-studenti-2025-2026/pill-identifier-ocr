"""
Napojenie na lokálny model gemma3:4b cez Ollama.

Všetky funkcie, ktoré vracajú dáta z modelu, vrátia pri chybe None,
aby aplikácia fungovala ďalej aj bez bežiacej Ollamy.
"""
import re
import json
import base64
import unicodedata
import requests

# --- KONFIGURÁCIA ---
OLLAMA_URL = "http://localhost:11434"
MODEL = "gemma3:4b"
KEEP_ALIVE = "30m"      # ako dlho ostane model po poslednom dotaze v pamäti
NUM_CTX = 8192          # veľkosť kontextu (predvolená v Ollame je menšia)
SECTION_LIMIT = 1500    # max. počet znakov z jednej sekcie letáku, ktorý pošleme modelu
DISCLAIMER = "Informácie sú len orientačné a nenahrádzajú radu lekára alebo lekárnika."

# --- ZÁKLAD ---

def is_available():
    """Beží Ollama a je stiahnutý model?"""
    try:
        models = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2).json()["models"]
        return any(m["name"] == MODEL for m in models)
    except (requests.RequestException, ValueError, KeyError):
        return False

def warmup():
    """Načíta model do pamäte vopred, aby prvý dotaz nečakal."""
    try:
        requests.post(f"{OLLAMA_URL}/api/generate",
                      json={"model": MODEL, "keep_alive": KEEP_ALIVE}, timeout=120)
    except requests.RequestException:
        pass

def ask_gemma(prompt, image_path=None, json_mode=False, timeout=180):
    """Pošle prompt (a voliteľne obrázok) do gemmy a vráti textovú odpoveď."""
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "options": {"temperature": 0, "num_ctx": NUM_CTX},
    }
    if image_path:
        with open(image_path, 'rb') as f:
            payload["images"] = [base64.b64encode(f.read()).decode('utf-8')]
    if json_mode:
        payload["format"] = "json"

    response = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()["response"].strip()

EMPTY_VALUES = {"", "null", "none", "n/a", "nezistené", "neuvedené"}

def _clean_value(value):
    """Model občas vráti "null" ako text, prevedieme to na skutočné None."""
    if isinstance(value, str):
        return None if value.strip().lower() in EMPTY_VALUES else value.strip()
    if isinstance(value, list):
        return [v for v in (_clean_value(v) for v in value) if v is not None]
    if isinstance(value, dict):
        # Kľúče bez diakritiky, model občas napíše "kontraindikácie" namiesto "kontraindikacie"
        return {_strip_accents(k): _clean_value(v) for k, v in value.items()}
    return value

def ask_json(prompt, image_path=None):
    """Ako ask_gemma, ale vráti dict (alebo None pri chybe)."""
    try:
        result = json.loads(ask_gemma(prompt, image_path=image_path, json_mode=True))
    except (requests.RequestException, ValueError, OSError):
        return None
    if not isinstance(result, dict):
        return None
    return _clean_value(result)

def _strip_accents(text):
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")

# --- POMOCNÉ FUNKCIE ---

def _section_text(value):
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value or "")

def _sections(pill_data, skip=("clinical_pharmacology",), only=None):
    """Poskladá sekcie letáku do jedného textu, každú skrátenú na SECTION_LIMIT znakov."""
    parts = []
    for key, value in (pill_data or {}).get("sections", {}).items():
        if key in skip or (only and key not in only):
            continue
        text = _section_text(value).strip()
        if text:
            parts.append(f"## {key}\n{text[:SECTION_LIMIT]}")
    return "\n\n".join(parts)

def _ingredient_names(pill_data):
    names = list((pill_data or {}).get("ingredient_en_candidates") or [])
    for key in ("matched_name", "ingredient_sk"):
        if pill_data and pill_data.get(key):
            names.append(pill_data[key])
    return [n for n in dict.fromkeys(names) if len(n) > 3]

def _mentions(text, names):
    """Vety z textu, ktoré spomínajú niektorú z látok."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s for s in sentences if any(n.lower() in s.lower() for n in names)]

def to_percent(value):
    try:
        return max(0, min(100, int(float(value))))
    except (TypeError, ValueError):
        return 0

# --- FUNKCIE APLIKÁCIE ---

def analyze_boxes(pill_names, ocr_text=None, image_path=None):
    """
    Rozpozná všetky lieky na fotke (alebo v OCR texte) a údaje z ich krabičiek.
    Vráti zoznam dictov (prázdny, ak žiadny liek nenašiel alebo gemma nebeží).
    Liek vyberá iba zo zoznamu, účinnú látku vráti aj po anglicky kvôli OpenFDA.
    """
    source = f'Text z OCR (môže obsahovať chyby, môže byť z viacerých krabičiek):\n"""{ocr_text}"""' if ocr_text \
        else "Na obrázku môže byť jedna alebo viac krabičiek liekov."
    prompt = (
        f"{source}\n\n"
        "Úloha: pre KAŽDÝ liek, ktorý tam je, urči:\n"
        "1. \"liek\": presný názov IBA zo zoznamu nižšie, inak null.\n"
        "2. Údaje z jeho krabičky. Čo na nej nie je, daj null.\n"
        "3. \"istota\": ako veľmi si si istý, že tam ten liek naozaj je (0-100).\n"
        "Každý liek uveď iba raz. Ak tam nie je žiadny liek, vráť prázdny zoznam.\n"
        "Odpovedz iba JSON v tvare:\n"
        "{\"lieky\": [{\"liek\": \"názov zo zoznamu alebo null\", "
        "\"nazov_na_krabicke\": \"...\", "
        "\"ucinna_latka\": \"po slovensky\", "
        "\"ucinna_latka_en\": \"medzinárodný anglický názov (INN)\", "
        "\"sila\": \"napr. 500 mg\", \"forma\": \"napr. tablety\", "
        "\"pocet\": \"napr. 30 tabliet\", \"vyrobca\": \"...\", \"istota\": 0-100}]}\n\n"
        "Zoznam liekov:\n" + "\n".join(pill_names)
    )
    result = ask_json(prompt, image_path=image_path) or {}
    boxes = result.get("lieky")
    return [b for b in boxes if isinstance(b, dict)] if isinstance(boxes, list) else []

def summarize(pill_name, pill_data, description=""):
    """Krátke slovenské zhrnutie letáku."""
    prompt = (
        f"Liek: {pill_name}\nÚčinná látka: {(pill_data or {}).get('ingredient_sk', '')}\n"
        f"Poznámky: {description}\n\n"
        f"Text z letáku:\n{_sections(pill_data)}\n\n"
        "Zhrň tieto informácie pre bežného človeka po slovensky. Používaj IBA text vyššie, "
        "nič si nevymýšľaj. Ak údaj v texte nie je, daj null. Každá položka max. 1 veta.\n"
        "Odpovedz iba JSON v tvare:\n"
        "{\"na_co\": \"...\", \"davkovanie\": \"...\", "
        "\"kontraindikacie\": [\"...\"], \"varovania\": [\"...\"], "
        "\"interakcie\": [\"...\"], \"vedlajsie_ucinky\": [\"...\"]}\n"
        "Zoznamy majú max. 4 položky."
    )
    return ask_json(prompt)

def answer_question(pill_name, pill_data, description, question):
    """Odpoveď na otázku k lieku, iba z dát lieku."""
    prompt = (
        f"Liek: {pill_name}\nÚčinná látka: {(pill_data or {}).get('ingredient_sk', '')}\n"
        f"Poznámky: {description}\n\n"
        f"Text z letáku:\n{_sections(pill_data)}\n\n"
        f"Otázka používateľa: {question}\n\n"
        "Odpovedz po slovensky v 1 až 4 vetách. Používaj IBA text vyššie. "
        "Iba ak text vyššie k otázke neobsahuje vôbec nič, napíš presne a nič viac: "
        "\"V podkladoch k tomuto lieku túto informáciu nemám.\""
    )
    try:
        return ask_gemma(prompt)
    except requests.RequestException:
        return None

def check_interaction(name_a, data_a, name_b, data_b):
    """Posúdi interakciu dvoch liekov z ich sekcií o interakciách."""
    sections = ("drug_interactions", "contraindications", "warnings_and_cautions", "warnings")
    text_a = _section_text((data_a or {}).get("sections", {}).get("drug_interactions"))
    text_b = _section_text((data_b or {}).get("sections", {}).get("drug_interactions"))
    # Vety, kde leták jedného lieku priamo spomína látku druhého
    direct = _mentions(text_a, _ingredient_names(data_b)) + _mentions(text_b, _ingredient_names(data_a))

    prompt = (
        f"Liek A: {name_a} (účinná látka: {', '.join(_ingredient_names(data_a))})\n"
        f"Liek B: {name_b} (účinná látka: {', '.join(_ingredient_names(data_b))})\n\n"
        f"Vety z letákov, ktoré priamo spomínajú druhý liek:\n"
        f"{chr(10).join(direct)[:2500] or '(žiadne)'}\n\n"
        f"Leták A:\n{_sections(data_a, only=sections)}\n\n"
        f"Leták B:\n{_sections(data_b, only=sections)}\n\n"
        "Posúď, či je známa interakcia medzi liekom A a B. Používaj IBA text vyššie. "
        "Ak letáky interakciu nespomínajú, daj riziko \"nezistené\".\n"
        "Odpovedz iba JSON v tvare:\n"
        "{\"riziko\": \"nezistené\" | \"nízke\" | \"stredné\" | \"vysoké\", "
        "\"vysvetlenie\": \"1-3 vety po slovensky\", \"odporucanie\": \"1 veta po slovensky\"}"
    )
    result = ask_json(prompt)
    if result is not None:
        result["priama_zmienka"] = bool(direct)
    return result
