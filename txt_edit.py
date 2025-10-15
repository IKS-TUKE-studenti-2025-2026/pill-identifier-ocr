import re

# zoznam účinných látok na odstránenie
ucinne_latky = [
    "paracetamol", "tramazolin", "ibuprofen", "ambroxol", "diklofenak",
    "cetirizin", "loratadin", "amoxicilin", "azithromycin", "pseudoefedrin"
]

def je_ucinna_latka(text):
    return text.lower() in ucinne_latky

def clean_medicine_name(line):
    # odstranenie zatvoriek
    line = re.sub(r"\(.*?\)", "", line)

    # ponechá čísla, odstráni mg/ml/g
    line = re.sub(r"(\d+)\s*(mg|ml|g|mcg)", r"\1", line, flags=re.IGNORECASE)

    # odstráni formy balenia
    line = re.sub(r"\b(tbl|cps|caps|sol|sir|ung|crm|inj|spray|neb|gtt|amp|gra|por|ml)\b", "", line, flags=re.IGNORECASE)

    # odstráni 1x10, 24x, 21x atď.
    line = re.sub(r"\b\d+\s*x\s*\d*\b", "", line)

    # čistí medzery
    line = re.sub(r"\s+", " ", line).strip()

    return line.title()

input_file = "vystup.txt"
output_file = "ciste_nazvy.txt"
vystup = set()

with open(input_file, "r", encoding="utf-8") as infile:
    for line in infile:
        cleaned = clean_medicine_name(line)
        if cleaned and not je_ucinna_latka(cleaned):
            vystup.add(cleaned)

with open(output_file, "w", encoding="utf-8") as outfile:
    for nazov in sorted(vystup):
        outfile.write(nazov + "\n")

print("✅ Hotovo! Uložené do ciste_nazvy.txt")
