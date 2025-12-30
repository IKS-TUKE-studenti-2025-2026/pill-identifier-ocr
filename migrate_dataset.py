import os
import shutil

# --- NASTAVENIA ---
# Cesta k tvojmu pôvodnému datasetu s fotkami
SOURCE_DATASET = r"C:\Users\fedor\Documents\GitHub\bakalarska_praca\dataset"

# Cesta, kde chceš mať nový dataset pre aplikáciu (v priečinku app)
DEST_APP_DATASET = r"C:\Users\fedor\Documents\GitHub\bakalarska_praca\app\dataset"

def duplicate_without_images():
    print("🚀 Spúšťam migráciu datasetu do aplikácie...")
    
    # 1. Skontrolujeme, či zdroj existuje
    if not os.path.exists(SOURCE_DATASET):
        print(f"❌ Chyba: Zdrojový priečinok {SOURCE_DATASET} nebol nájdený.")
        return

    # 2. Vytvoríme cieľový priečinok app/dataset, ak neexistuje
    if not os.path.exists(DEST_APP_DATASET):
        os.makedirs(DEST_APP_DATASET)
        print(f"📁 Vytvorený hlavný priečinok: {DEST_APP_DATASET}")

    count_folders = 0
    count_files = 0

    # 3. Prechádzame priečinky v pôvodnom datasete
    for folder_name in os.listdir(SOURCE_DATASET):
        source_folder_path = os.path.join(SOURCE_DATASET, folder_name)

        if os.path.isdir(source_folder_path):
            # Vytvoríme rovnaký pod-priečinok v app/dataset
            dest_folder_path = os.path.join(DEST_APP_DATASET, folder_name)
            
            if not os.path.exists(dest_folder_path):
                os.makedirs(dest_folder_path)
            
            count_folders += 1

            # 4. Hľadáme a kopírujeme iba JSON súbory
            for item in os.listdir(source_folder_path):
                if item.lower().endswith('.json'):
                    s_file = os.path.join(source_folder_path, item)
                    d_file = os.path.join(dest_folder_path, item)
                    
                    shutil.copy2(s_file, d_file)
                    count_files += 1

    print("-" * 40)
    print(f"✅ HOTOVO!")
    print(f"📂 Vytvorených priečinkov liekov: {count_folders}")
    print(f"📄 Skopírovaných JSON súborov: {count_files}")
    print(f"⚠️ Žiadne obrázky neboli skopírované.")

if __name__ == "__main__":
    duplicate_without_images()