import easyocr
import torch
import os
import numpy as np
import cv2
from fuzzywuzzy import fuzz
from PIL import Image
import csv
import re

# --- ČISTENIE TEXTU (Ešte agresívnejšie na šum) ---
def clean_text(text):
    if not text: return ""
    # Odstránime dávkovanie a špeciálne znaky
    text = re.sub(r'\d+\s*(mg|ml|g|tbl|cps|tablety|ug|%|mgml)', '', text, flags=re.IGNORECASE)
    # Ponecháme len písmená a medzery
    return re.sub(r'[^a-zA-Z\s]', '', text).lower().strip()

def read_pill_names(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return [line.strip() for line in file.readlines()]

def safe_load_image(image_path):
    try:
        img_array = np.fromfile(image_path, np.uint8)
        return cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    except: return None

# --- PREPROCESSING ---
def get_optimized_variants(img):
    if img is None: return []
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    en_gray = clahe.apply(gray)
    resized = cv2.resize(en_gray, None, fx=2, fy=2, interpolation=cv2.INTER_LANCZOS4)
    # Skúsime len jeden, ale kvalitný variant na zníženie šumu
    return [resized]

# --- HLAVNÁ LOGIKA ---
reader = easyocr.Reader(['en', 'sk'], gpu=True)
dataset_path = r"C:\Users\fedor\Documents\GitHub\bakalarska_praca\dataset"
pill_names_file = r"C:\Users\fedor\Documents\GitHub\bakalarska_praca\zoznam_liekov.txt"
pill_names_list = read_pill_names(pill_names_file)

spravne = 0
nespravne = 0

with open('ocr_results.csv', mode='w', newline='', encoding='utf-8') as csvfile:
    fieldnames = ['Detected Text', 'Guessed Pill Name', 'Match Percentage', 'Correct Guess', 'Correct Folder']
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()

    folders = sorted([f for f in os.listdir(dataset_path) if os.path.isdir(os.path.join(dataset_path, f))])
    
    for folder_name in folders[:50]: 
        folder_path = os.path.join(dataset_path, folder_name)
        print(f"Spracovávam: {folder_name}")

        for image_file in os.listdir(folder_path):
            if image_file.lower().endswith(('.jpg', '.jpeg', '.png')):
                image_path = os.path.join(folder_path, image_file)
                raw_img = safe_load_image(image_path)
                if raw_img is None: continue

                # Spustíme OCR na upravenom obrázku
                variants = get_optimized_variants(raw_img)
                full_detected_text = ""
                for var in variants:
                    results = reader.readtext(var, detail=0, paragraph=True, text_threshold=0.2)
                    full_detected_text += " " + " ".join(results)

                # Vyčistíme detekovaný text
                ocr_cleaned = clean_text(full_detected_text)
                
                best_match = None
                max_score = 0

                # --- NOVÝ MATCHING ALGORITMUS ---
                for pill_name in pill_names_list:
                    pill_cleaned = clean_text(pill_name)
                    if not pill_cleaned: continue

                    # 1. Partial Ratio nájde názov aj v "bordeli"
                    partial = fuzz.partial_ratio(pill_cleaned, ocr_cleaned)
                    
                    # 2. Token Set Ratio ignoruje poradie slov
                    token = fuzz.token_set_ratio(pill_cleaned, ocr_cleaned)
                    
                    # Kombinované skóre (vážený priemer)
                    current_score = (partial * 0.7) + (token * 0.3)

                    # 3. FUZZY BONUS ZA CORE PART (napr. Betaloc)
                    core_part = pill_cleaned.split()[0]
                    # Ak sa prvé slovo lieku podobá na čokoľvek v OCR, pridaj bonus
                    if fuzz.partial_ratio(core_part, ocr_cleaned) > 85:
                        current_score += 25 

                    if current_score > max_score:
                        max_score = current_score
                        best_match = pill_name

                final_percentage = min(100, int(max_score))

                # Vyhodnotenie
                is_correct = "No"
                # Ak sme našli zhodu nad 70% s novým scoringom, je to vysoko pravdepodobné
                if final_percentage >= 70: 
                    # Overíme, či sa hádanka zhoduje s názvom priečinka
                    if best_match and fuzz.token_set_ratio(best_match.lower(), folder_name.lower()) > 75:
                        is_correct = "Yes"
                        spravne += 1
                    else: nespravne += 1
                else: nespravne += 1

                writer.writerow({
                    'Detected Text': full_detected_text.strip(),
                    'Guessed Pill Name': best_match,
                    'Match Percentage': final_percentage,
                    'Correct Guess': is_correct,
                    'Correct Folder': folder_name
                })

total = spravne + nespravne
precision = (spravne / total) * 100 if total > 0 else 0
print(f"\n--- NOVÝ VÝSLEDOK ---\nSprávne: {spravne} | Nesprávne: {nespravne}\nPresnosť: {precision:.2f}%")