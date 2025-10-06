
import os
from icrawler.builtin import GoogleImageCrawler

# Cesta k súboru s názvami liekov
file_path = "dataset/lieky.txt"

# Vytvor koreňový priečinok pre dataset
os.makedirs("dataset", exist_ok=True)

# Načítaj zoznam liekov
with open(file_path, "r", encoding="utf-8") as f:
    drugs = [line.strip() for line in f.readlines() if line.strip()]

print(f"Načítaných {len(drugs)} liekov.")

# Pre každý liek stiahni 5 obrázkov
for drug in drugs:
    # vytvor priečinok s názvom lieku
    drug_dir = os.path.join("dataset", drug.replace(" ", "_"))
    os.makedirs(drug_dir, exist_ok=True)

    print(f"📦 Sťahujem obrázky pre: {drug}")

    # Nastav crawler
    crawler = GoogleImageCrawler(storage={'root_dir': drug_dir})
    crawler.crawl(
        keyword=f"{drug} obal lieku",
        max_num=5,
        filters={'size': 'medium'}
    )

print("✅ Hotovo! Všetky obrázky sú uložené v priečinku 'dataset'.")
