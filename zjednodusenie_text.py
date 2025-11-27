import json
import os

# Funkcia na premenovanie "drug_name" v JSON súbore podľa názvu priečinka
def rename_drug_name_in_json(drug_folder_path, json_file_path):
    # Získame celý názov priečinka (vrátane všetkých informácií o dávkovaní a obale)
    folder_name = os.path.basename(drug_folder_path)
    
    # Načítať JSON súbor
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Zmeniť "drug_name" na celý názov lieku
    data['drug_name'] = folder_name  # Použijeme celý názov priečinka ako nový názov lieku
    
    # Uložiť upravený JSON súbor späť
    with open(json_file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    
    print(f"Premenovaný názov lieku v JSON: {folder_name}")

# Cesta k hlavnému priečinku
base_folder = "C:/Users/fedor/Documents/GitHub/bakalarska_praca/dataset"

# Prejdeme všetkými priečinkami v "dataset" priečinku
def process_all_drugs(base_folder):
    not_renamed = []  # Zoznam priečinkov, ktoré neboli premenované
    
    # Prejdeme všetkými priečinkami v "dataset" priečinku
    for drug_folder_name in os.listdir(base_folder):
        drug_folder_path = os.path.join(base_folder, drug_folder_name)
        
        # Skontrolujeme, či ide o priečinok
        if os.path.isdir(drug_folder_path):
            json_file_path = os.path.join(drug_folder_path, "interactions.json")
            
            # Ak existuje JSON súbor, premenováme drug_name
            if os.path.isfile(json_file_path):
                try:
                    rename_drug_name_in_json(drug_folder_path, json_file_path)
                except Exception as e:
                    print(f"Chyba pri spracovaní priečinka {drug_folder_name}: {e}")
            else:
                not_renamed.append(drug_folder_name)
    
    # Vypíšeme priečinky, ktoré neboli premenované (ktoré neobsahujú interactions.json)
    if not_renamed:
        print("\nPriečinky, ktoré neboli premenované, pretože neobsahujú interactions.json:")
        for folder in not_renamed:
            print(folder)

# Zavoláme funkciu na premenovanie pre všetky priečinky
process_all_drugs(base_folder)
