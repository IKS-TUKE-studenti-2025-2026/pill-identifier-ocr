import os
import json
import threading
import requests
import numpy as np
import cv2
import easyocr
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import llm
from recognition import clean_text, identify_pills, load_pill_names, METHOD_LABELS

app = Flask(__name__)

# --- KONFIGURÁCIA ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
DATASET_PATH = os.path.join(BASE_DIR, 'dataset')
PILL_NAMES_FILE = os.path.join(BASE_DIR, 'zoznam_liekov.txt')

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
reader = easyocr.Reader(['en', 'sk'], gpu=True)

# Dáta naposledy zobrazených liekov (aj tých z OpenFDA), aby ich vedeli použiť API pre gemmu
pill_cache = {}

# Model sa načíta do pamäte na pozadí hneď pri štarte
threading.Thread(target=llm.warmup, daemon=True).start()

# --- POMOCNÉ FUNKCIE ---

def fetch_pill_data_from_api(query, field="openfda.brand_name"):
    """Získanie dát o účinných látkach z OpenFDA API."""
    try:
        url = f"https://api.fda.gov/drug/label.json?search={field}:{query}&limit=1"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            res = response.json()['results'][0]
            return {
                "ingredient_sk": res.get('active_ingredient', ['Nezistené'])[0],
                "disease_flags": ["Externý zdroj"],
                "sections": {
                    "Indikácie": res.get('indications_and_usage', ['Nezadané'])[0],
                    "Varovania": res.get('warnings', ['Nezadané'])[0],
                    "Dávkovanie": res.get('dosage_and_administration', ['Nezadané'])[0],
                    "Vedľajšie_účinky": res.get('adverse_reactions', ['Nezadané'])[0]
                }
            }
    except:
        return None
    return None

def load_local_pill(name):
    """Načíta interactions.json a dataset.txt z datasetu (alebo None, "")."""
    json_path = os.path.join(DATASET_PATH, name, 'interactions.json')
    txt_path = os.path.join(DATASET_PATH, name, 'dataset.txt')
    p_data, p_desc = None, ""
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f: p_data = json.load(f)
    if os.path.exists(txt_path):
        with open(txt_path, 'r', encoding='utf-8') as f: p_desc = f.read()
    return p_data, p_desc

def get_pill(name):
    """Dáta lieku pre API. Názov musí byť zo zoznamu alebo z cache (ochrana cesty k súborom)."""
    if name in pill_cache:
        return pill_cache[name]
    if name in load_pill_names(PILL_NAMES_FILE):
        p_data, p_desc = load_local_pill(name)
        if p_data:
            return p_data, p_desc
    return None, ""

def make_pill(name, score, method, box, p_data, p_desc):
    """Jeden nájdený liek pre šablónu."""
    box = box or {}
    details = {label: box.get(key) for key, label in
               [("sila", "Sila"), ("forma", "Forma"), ("pocet", "Balenie"), ("vyrobca", "Výrobca")]
               if isinstance(box.get(key), str) and box.get(key).strip()}
    return {"name": name, "score": score, "method_label": METHOD_LABELS.get(method),
            "details": details, "data": p_data, "description": p_desc}

# --- ROUTES ---

@app.route('/', methods=['GET', 'POST'])
def index():
    pill_names = load_pill_names(PILL_NAMES_FILE)
    llm_on = llm.is_available()

    if request.method == 'POST':
        file = request.files.get('image')
        if not file or file.filename == '':
            return render_template('index.html', message="Nebol prijatý žiaden súbor.", llm_on=llm_on)

        filename = secure_filename(file.filename)
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(image_path)

        img_array = np.fromfile(image_path, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

        if img is None:
            return render_template('index.html', message="Chyba: Nepodarilo sa spracovať obrázok.", llm_on=llm_on)

        # OCR Analýza (odseky nechávame zvlášť, na fotke môže byť viac krabičiek)
        ocr_blocks = reader.readtext(img, detail=0, paragraph=True)
        full_text = " ".join(ocr_blocks)

        # Rozpoznanie: fuzzy matching + gemma (fotka)
        found, unknown = identify_pills(ocr_blocks, image_path, pill_names, use_llm=llm_on)

        pills = []
        for item in found:
            p_data, p_desc = load_local_pill(item["name"])
            if p_data is None:
                p_data = fetch_pill_data_from_api(item["name"])
            pills.append(make_pill(item["name"], item["score"], item["method"], item["box"], p_data, p_desc))

        # Lieky mimo zoznamu: OpenFDA podľa účinnej látky od gemmy
        for box in unknown:
            ingredient = box.get("ucinna_latka_en")
            if not isinstance(ingredient, str) or not ingredient.strip():
                continue
            p_data = fetch_pill_data_from_api(f'"{ingredient.strip()}"', field="openfda.generic_name")
            name = str(box.get("nazov_na_krabicke") or ingredient).strip().upper()
            if p_data and name not in [p["name"] for p in pills]:
                pills.append(make_pill(name, llm.to_percent(box.get("istota")), "openfda", box,
                                       p_data, "Informácie automaticky načítané z OpenFDA."))

        # Bez gemmy ako predtým: OpenFDA podľa prvého slova z OCR
        if not pills and not llm_on:
            words = clean_text(full_text).split()
            p_data = fetch_pill_data_from_api(words[0]) if words else None
            if p_data:
                pills.append(make_pill(words[0].upper(), 90, "openfda", None,
                                       p_data, "Informácie automaticky načítané z OpenFDA."))

        for pill in pills:
            if pill["data"]:
                pill_cache[pill["name"]] = (pill["data"], pill["description"])

        names = [p["name"] for p in pills if p["data"]]
        message = None if pills else "Žiadna zhoda: liek sa na obrázku nepodarilo rozpoznať."

        return render_template('index.html',
                               message=message,
                               detected_text=full_text,
                               pills=pills,
                               pair_checks=[(a, b) for i, a in enumerate(names) for b in names[i + 1:]],
                               all_pills=pill_names,
                               llm_on=llm_on,
                               disclaimer=llm.DISCLAIMER)

    return render_template('index.html', llm_on=llm_on)

# --- API PRE GEMMU (volá ich JavaScript po zobrazení výsledku) ---

@app.route('/api/summary', methods=['POST'])
def api_summary():
    name = (request.get_json(silent=True) or {}).get('pill', '')
    p_data, p_desc = get_pill(name)
    if not p_data:
        return jsonify(error="Liek sa nenašiel."), 404

    # Zhrnutie liekov z datasetu sa ukladá, aby sa generovalo iba raz
    cache_path = os.path.join(DATASET_PATH, name, 'summary_sk.json')
    if os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))

    summary = llm.summarize(name, p_data, p_desc)
    if summary is None:
        return jsonify(error="Gemma nie je dostupná."), 503
    if os.path.isdir(os.path.join(DATASET_PATH, name)):
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    return jsonify(summary)

@app.route('/api/ask', methods=['POST'])
def api_ask():
    body = request.get_json(silent=True) or {}
    question = str(body.get('question', '')).strip()[:500]
    p_data, p_desc = get_pill(body.get('pill', ''))
    if not p_data or not question:
        return jsonify(error="Chýba liek alebo otázka."), 400

    answer = llm.answer_question(body['pill'], p_data, p_desc, question)
    if answer is None:
        return jsonify(error="Gemma nie je dostupná."), 503
    return jsonify(answer=answer)

@app.route('/api/interaction', methods=['POST'])
def api_interaction():
    body = request.get_json(silent=True) or {}
    name_a, name_b = body.get('pill', ''), body.get('other', '')
    data_a, _ = get_pill(name_a)
    data_b, _ = get_pill(name_b)
    if not data_a or not data_b:
        return jsonify(error="Liek sa nenašiel."), 404

    result = llm.check_interaction(name_a, data_a, name_b, data_b)
    if result is None:
        return jsonify(error="Gemma nie je dostupná."), 503
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
