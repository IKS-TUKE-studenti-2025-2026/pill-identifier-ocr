import pytesseract
from PIL import Image
import os
import csv
from difflib import SequenceMatcher

# Nastavenie cesty k Tesseract exe súboru
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Cesta k priečinku s datasetom
dataset_path = r"dataset"  # Tu upravte cestu k svojmu datasetu

# Funkcia na uloženie textu do CSV
def save_to_csv(data, output_filename):
    header = ['folder', 'image', 'expected_brand', 'ocr_excerpt', 'score_brand', 'status', 'variant']
    
    # Otvorenie a zapisovanie do CSV
    with open(output_filename, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(header)  # Zapíše hlavičku
        for row in data:
            writer.writerow(row)

# Funkcia na výpočet skóre podobnosti medzi očakávaným názvom a OCR textom
def calculate_similarity(expected, actual):
    return SequenceMatcher(None, expected.lower(), actual.lower()).ratio() * 100

# Funkcia na spracovanie obrázkov a extrakciu textu
def extract_and_process_image(drug_folder, image_file, expected_brand):
    img_path = os.path.join(drug_folder, image_file)
    try:
        # Načítanie obrázka
        img = Image.open(img_path)
        
        # Použitie Tesseract OCR na extrakciu textu
        ocr_text = pytesseract.image_to_string(img)
        
        # Výpočet skóre podobnosti medzi očakávanou značkou a extrahovaným textom
        score = calculate_similarity(expected_brand, ocr_text)
        
        # Stanovenie stavu
        status = "OK" if score >= 90 else "KO"  # Ak je skóre vyššie ako 90, považujeme to za OK
        variant = "center|psm=6"  # Tvoje požiadavky na variant (prípadne môžeš upravit podľa potreby)
        
        # Vytvorenie riadku do CSV
        return [drug_folder, image_file, expected_brand, ocr_text.strip(), round(score, 2), status, variant]
    
    except Exception as e:
        print(f"Chyba pri spracovaní obrázka {image_file}: {e}")
        return [drug_folder, image_file, expected_brand, "", 0, "KO", ""]  # Ak nastane chyba, vrátime prázdny text a KO status

# Funkcia na spracovanie všetkých obrázkov v priečinku lieku
def process_all_drugs_in_dataset(dataset_path):
    data = []
    
    for drug_folder in os.listdir(dataset_path):
        drug_folder_path = os.path.join(dataset_path, drug_folder)
        if os.path.isdir(drug_folder_path):
            print(f"Spracovávam liek: {drug_folder}")
            
            # Otvoríme súbor dataset.txt a načítame očakávaný názov značky
            dataset_file_path = os.path.join(drug_folder_path, "dataset.txt")
            if os.path.exists(dataset_file_path):
                with open(dataset_file_path, "r", encoding="utf-8") as file:
                    expected_brand = file.readline().strip()  # Očakávaný názov značky lieku je v prvej línii
                
                # Prejdeme všetky obrázky v priečinku lieku
                images = [f for f in os.listdir(drug_folder_path) if f.endswith('.jpg') or f.endswith('.png')]
                
                for image_file in images:
                    row = extract_and_process_image(drug_folder_path, image_file, expected_brand)
                    data.append(row)
    
    # Uloženie výsledkov do CSV
    save_to_csv(data, "output.csv")
    print("Spracovanie dokončené, výstup je v súbore output.csv")

# Spustenie spracovania všetkých liekov
process_all_drugs_in_dataset(dataset_path)
