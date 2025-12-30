import os
import re
import json
import numpy as np
import cv2
import easyocr
from flask import Flask, render_template, request
from fuzzywuzzy import fuzz
from werkzeug.utils import secure_filename

app = Flask(__name__)

# --- KONFIGURÁCIA ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PILL_NAMES_FILE = os.path.join(BASE_DIR, 'zoznam_liekov.txt')
DATASET_PATH = os.path.join(BASE_DIR, 'dataset')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Inicializácia OCR presne ako v teste
reader = easyocr.Reader(['en', 'sk'], gpu=True)

# --- IDENTICKÉ FUNKCIE AKO V TESTE ---

def clean_text(text):
    if not text: return ""
    # Odstránenie dávkovania a jednotiek
    text = re.sub(r'\d+\s*(mg|ml|g|tbl|cps|tablety|ug|%|mgml)', '', text, flags=re.IGNORECASE)
    # Ponechanie len písmen a medzier
    return re.sub(r'[^a-zA-Z\s]', '', text).lower().strip()

def get_image_variants(img):
    """Vytvorí 3 varianty obrázka presne ako v tvojom úspešnom teste."""
    if img is None: return []

    # Variant 1: Grayscale + resize (Lanczos4)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray_res = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_LANCZOS4)
    
    # Variant 2: Adaptívne prahovanie (Threshold)
    thresh = cv2.adaptiveThreshold(gray_res, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    
    # Variant 3: CLAHE (Kontrast)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    contrast_img = clahe.apply(gray_res)

    return [gray_res, thresh, contrast_img]

def find_pill_data(folder_name):
    json_path = os.path.join(DATASET_PATH, folder_name, 'interactions.json')
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

# --- HLAVNÝ MATCHING (Identický s ocr_batch_test) ---

def find_best_match(full_detected_text, pill_names_list):
    ocr_cleaned = clean_text(full_detected_text)
    if not ocr_cleaned: return None, 0

    best_match = None
    max_score = 0

    for pill_name in pill_names_list:
        pill_cleaned = clean_text(pill_name)
        if not pill_cleaned: continue

        # Identický scoring 0.7/0.3
        partial = fuzz.partial_ratio(pill_cleaned, ocr_cleaned)
        token = fuzz.token_set_ratio(pill_cleaned, ocr_cleaned)
        current_score = (partial * 0.7) + (token * 0.3)

        # Fuzzy bonus za Core Part
        core_part = pill_cleaned.split()[0]
        if fuzz.partial_ratio(core_part, ocr_cleaned) > 85:
            current_score += 25 

        if current_score > max_score:
            max_score = current_score
            best_match = pill_name

    return best_match, min(100, int(max_score))

# --- ROUTES ---

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        file = request.files.get('image')
        if not file or file.filename == '':
            return render_template('index.html', message="Nebol vybraný žiaden súbor.")

        # Uloženie
        filename = secure_filename(file.filename)
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(image_path)

        # Načítanie (safe load s diakritikou)
        img_array = np.fromfile(image_path, np.uint8)
        raw_img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        if raw_img is None:
            return render_template('index.html', message="Chyba pri načítaní obrázka.")

        # Získanie variantov a OCR (identicky s testom)
        variants = get_image_variants(raw_img)
        full_detected_text = ""
        
        for var in variants:
            # text_threshold=0.2 podľa tvojich úprav
            results = reader.readtext(var, detail=0, paragraph=True, text_threshold=0.2)
            if results:
                full_detected_text += " " + " ".join(results)

        # Ak by varianty zlyhali, skúsime surový obrázok
        if not full_detected_text.strip():
            results = reader.readtext(raw_img, detail=0, paragraph=True)
            full_detected_text = " ".join(results)

        # Vyhľadanie zhody
        with open(PILL_NAMES_FILE, 'r', encoding='utf-8') as f:
            pill_names_list = [line.strip() for line in f.readlines()]
            
        best_match, match_percentage = find_best_match(full_detected_text, pill_names_list)

        # Zobrazenie (tvoj prah 70% z testu)
        if best_match and match_percentage >= 70:
            pill_data = find_pill_data(best_match)
            return render_template('index.html', 
                                   detected_text=full_detected_text.strip(), 
                                   best_match=best_match, 
                                   match_percentage=match_percentage, 
                                   pill_data=pill_data)
        else:
            return render_template('index.html', 
                                   detected_text=full_detected_text.strip(),
                                   message=f"Liek sa nepodarilo určiť. (Najvyššia nájdená zhoda: {match_percentage}%)")

    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)