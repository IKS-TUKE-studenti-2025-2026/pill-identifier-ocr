import os
import shutil

# --- NASTAVENIA ---
# Cesta k tvojmu pôvodnému datasetu s fotkami
SOURCE_DATASET = r"C:\Users\fedor\Documents\GitHub\bakalarska_praca\dataset"

# Cesta, kde chceš mať nový dataset pre aplikáciu (v priečinku app)
DEST_APP_DATASET = r"C:\Users\fedor\Documents\GitHub\bakalarska_praca\app\dataset"

def duplicate_data_files():
    print("🚀 Spúšťam rozšírenú migráciu (JSON + TXT)...")
    
    if not os.path.exists(SOURCE_DATASET):
        print(f"❌ Chyba: Zdrojový priečinok {SOURCE_DATASET} nebol nájdený.")
        return

    if not os.path.exists(DEST_APP_DATASET):
        os.makedirs(DEST_APP_DATASET)

    count_folders = 0
    count_json = 0
    count_txt = 0

    for folder_name in os.listdir(SOURCE_DATASET):
        source_folder_path = os.path.join(SOURCE_DATASET, folder_name)

        if os.path.isdir(source_folder_path):
            dest_folder_path = os.path.join(DEST_APP_DATASET, folder_name)
            
            if not os.path.exists(dest_folder_path):
                os.makedirs(dest_folder_path)
            
            count_folders += 1

            # Hľadáme JSON súbory a súbor dataset.txt
            for item in os.listdir(source_folder_path):
                item_lower = item.lower()
                
                # Kopírujeme interactions.json ALEBO dataset.txt
                if item_lower.endswith('.json') or item_lower == 'dataset.txt':
                    s_file = os.path.join(source_folder_path, item)
                    d_file = os.path.join(dest_folder_path, item)
                    
                    shutil.copy2(s_file, d_file)
                    
                    if item_lower.endswith('.json'):
                        count_json += 1
                    else:
                        count_txt += 1

    print("-" * 40)
    print(f"✅ HOTOVO!")
    print(f"📂 Spracovaných priečinkov liekov: {count_folders}")
    print(f"📄 Skopírovaných JSON súborov: {count_json}")
    print(f"📝 Skopírovaných popisov (dataset.txt): {count_txt}")

if __name__ == "__main__":
    duplicate_data_files()