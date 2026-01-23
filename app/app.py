import os
import re
import json
import requests
import numpy as np
import cv2
import easyocr
from flask import Flask, render_template, request
from fuzzywuzzy import fuzz
from werkzeug.utils import secure_filename

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

# --- POMOCNÉ FUNKCIE ---

def clean_text(text):
    if not text: return ""
    # Odstránenie jednotiek a dávkovania pre presnejší matching
    text = re.sub(r'\d+\s*(mg|ml|g|tbl|cps|tablety|ug|%|mgml)', '', text, flags=re.IGNORECASE)
    return re.sub(r'[^a-zA-Z\s]', '', text).lower().strip()

def fetch_pill_data_from_api(pill_name):
    """Získanie dát o účinných látkach z OpenFDA API."""
    try:
        url = f"https://api.fda.gov/drug/label.json?search=openfda.brand_name:{pill_name}&limit=1"
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

def find_best_match(full_detected_text, pill_names_list):
    ocr_cleaned = clean_text(full_detected_text)
    if not ocr_cleaned: return None, 0
    best_match, max_score = None, 0
    for pill_name in pill_names_list:
        pill_cleaned = clean_text(pill_name)
        score = (fuzz.partial_ratio(pill_cleaned, ocr_cleaned) * 0.7) + (fuzz.token_set_ratio(pill_cleaned, ocr_cleaned) * 0.3)
        if score > max_score:
            max_score = score
            best_match = pill_name
    return best_match, int(max_score)

# --- ROUTES ---

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        file = request.files.get('image')
        if not file or file.filename == '':
            return render_template('index.html', message="Nebol prijatý žiaden súbor.")

        filename = secure_filename(file.filename)
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(image_path)

        img_array = np.fromfile(image_path, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

        if img is None:
            return render_template('index.html', message="Chyba: Nepodarilo sa spracovať obrázok.")

        # OCR Analýza
        results = reader.readtext(img, detail=0, paragraph=True)
        full_text = " ".join(results)
        
        # Hľadanie v lokálnom zozname
        match_name, score = None, 0
        if os.path.exists(PILL_NAMES_FILE):
            with open(PILL_NAMES_FILE, 'r', encoding='utf-8') as f:
                pill_names = [line.strip() for line in f.readlines()]
            match_name, score = find_best_match(full_text, pill_names)

        p_data, p_desc = None, ""
        
        if match_name and score >= 70:
            json_path = os.path.join(DATASET_PATH, match_name, 'interactions.json')
            txt_path = os.path.join(DATASET_PATH, match_name, 'dataset.txt')
            
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f: p_data = json.load(f)
            else:
                p_data = fetch_pill_data_from_api(match_name)
                
            if os.path.exists(txt_path):
                with open(txt_path, 'r', encoding='utf-8') as f: p_desc = f.read()
        else:
            words = clean_text(full_text).split()
            if words:
                p_data = fetch_pill_data_from_api(words[0])
                if p_data:
                    match_name = words[0].upper()
                    score = 90
                    p_desc = "Informácie automaticky načítané z OpenFDA."

        return render_template('index.html', 
                               detected_text=full_text,
                               best_match=match_name, 
                               match_percentage=score, 
                               pill_data=p_data,
                               pill_description=p_desc)

    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)