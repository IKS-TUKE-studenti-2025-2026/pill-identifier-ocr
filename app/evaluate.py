"""
Porovnanie metód rozpoznania lieku na označených fotkách (experiment do bakalárky).

Fotky daj do eval/images/ a do eval/labels.csv zapíš správne lieky:
    subor,liek
    paralen_500.jpg,PARALEN 500
    dva_lieky.jpg,PARALEN 500;ANOPYRIN 100 mg
Viac liekov na jednej fotke oddeľ bodkočiarkou. Ak liek na fotke nie je v zozname,
nechaj stĺpec liek prázdny (správna odpoveď je "nič").
Fotka je rozpoznaná správne, iba ak metóda našla presne tie isté lieky (nič navyše, nič nechýba).

Použitie:
    python evaluate.py
Výsledky: tabuľka v konzole, eval/vysledky.csv (každá fotka) a eval/suhrn.csv (každá metóda).
"""
import os
import csv
import sys
import time
import easyocr
import llm
from recognition import find_best_match, load_pill_names, accept_boxes, identify_pills, FUZZY_MIN

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EVAL_DIR = os.path.join(BASE_DIR, 'eval')
IMAGES_DIR = os.path.join(EVAL_DIR, 'images')
LABELS_FILE = os.path.join(EVAL_DIR, 'labels.csv')
PILL_NAMES_FILE = os.path.join(BASE_DIR, 'zoznam_liekov.txt')

METHODS = ["fuzzy", "ocr_gemma", "vision_gemma", "kombinacia"]

# --- METÓDY (každá vráti množinu názvov zo zoznamu) ---

def gemma_names(boxes, pill_names, ocr_text, from_photo):
    """Rovnaký výber ako v aplikácii (hranica istoty + poistka proti halucináciám)."""
    accepted, _ = accept_boxes(boxes, pill_names, ocr_text, from_photo)
    return {name for name, _, _ in accepted}

def method_fuzzy(ocr_blocks, image_path, pill_names):
    """Pôvodná aplikácia: jeden najlepší liek z celého textu."""
    name, score = find_best_match(" ".join(ocr_blocks), pill_names)
    return {name} if score >= FUZZY_MIN else set()

def method_ocr_gemma(ocr_blocks, image_path, pill_names):
    text = " ".join(ocr_blocks)
    return gemma_names(llm.analyze_boxes(pill_names, ocr_text=text), pill_names, text, from_photo=False)

def method_vision_gemma(ocr_blocks, image_path, pill_names):
    text = " ".join(ocr_blocks)
    return gemma_names(llm.analyze_boxes(pill_names, image_path=image_path), pill_names, text, from_photo=True)

def method_combination(ocr_blocks, image_path, pill_names):
    """Celý postup z aplikácie: fuzzy matching + gemma (fotka)."""
    pills, _ = identify_pills(ocr_blocks, image_path, pill_names)
    return {p["name"] for p in pills}

METHOD_FUNCS = {
    "fuzzy": method_fuzzy,
    "ocr_gemma": method_ocr_gemma,
    "vision_gemma": method_vision_gemma,
    "kombinacia": method_combination,
}

# --- HLAVNÝ PROGRAM ---

def load_labels():
    with open(LABELS_FILE, 'r', encoding='utf-8') as f:
        return [(row["subor"].strip(), {n.strip() for n in row["liek"].split(";") if n.strip()})
                for row in csv.DictReader(f)]

def main():
    if not llm.is_available():
        sys.exit(f"Ollama nebeží alebo chýba model {llm.MODEL}.")

    pill_names = load_pill_names(PILL_NAMES_FILE)
    labels = load_labels()
    reader = easyocr.Reader(['en', 'sk'], gpu=True)
    llm.warmup()  # aby sa čas načítania modelu nezapočítal do prvej fotky

    rows = []
    for filename, expected in labels:
        image_path = os.path.join(IMAGES_DIR, filename)
        if not os.path.exists(image_path):
            print(f"Preskakujem {filename}: súbor neexistuje.")
            continue

        start = time.time()
        ocr_blocks = reader.readtext(image_path, detail=0, paragraph=True)
        ocr_time = time.time() - start
        print(f"\n{filename} (správne: {'; '.join(sorted(expected)) or 'nič'})")

        for method in METHODS:
            start = time.time()
            predicted = METHOD_FUNCS[method](ocr_blocks, image_path, pill_names)
            elapsed = time.time() - start
            # Metódy, ktoré používajú OCR text, platia aj čas OCR
            if method != "vision_gemma":
                elapsed += ocr_time
            correct = predicted == expected
            predicted_text = "; ".join(sorted(predicted))
            print(f"  {method:<13} {'OK ' if correct else 'ZLE'} {predicted_text or 'nič':<40} {elapsed:5.1f} s")
            rows.append({"subor": filename, "spravne": "; ".join(sorted(expected)), "metoda": method,
                         "vysledok": predicted_text, "spravne_rozpoznane": int(correct),
                         "cas_s": round(elapsed, 2)})

    if not rows:
        sys.exit("Žiadne fotky na vyhodnotenie.")

    with open(os.path.join(EVAL_DIR, 'vysledky.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    summary = []
    for method in METHODS:
        method_rows = [r for r in rows if r["metoda"] == method]
        summary.append({
            "metoda": method,
            "presnost_%": round(100 * sum(r["spravne_rozpoznane"] for r in method_rows) / len(method_rows), 1),
            "priemerny_cas_s": round(sum(r["cas_s"] for r in method_rows) / len(method_rows), 2),
            "pocet_fotiek": len(method_rows),
        })

    with open(os.path.join(EVAL_DIR, 'suhrn.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=summary[0].keys())
        writer.writeheader()
        writer.writerows(summary)

    print(f"\n{'Metóda':<15}{'Presnosť':>10}{'Čas':>10}")
    for s in summary:
        print(f"{s['metoda']:<15}{s['presnost_%']:>9}%{s['priemerny_cas_s']:>9}s")
    print(f"\nUložené do {EVAL_DIR}\\vysledky.csv a suhrn.csv")

if __name__ == '__main__':
    main()
