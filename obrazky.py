import os
import io
import time
import requests
from duckduckgo_search import DDGS
from PIL import Image, ImageOps, ImageEnhance
import random

# hlavný priečinok s liekmi
dataset_dir = "dataset"

# počet obrázkov na stiahnutie pre každý liek
num_images = 3

# cieľová veľkosť obrázka (pre OCR tréning)
TARGET_SIZE = (512, 512)

# Rate limiting settings
DELAY_BETWEEN_SEARCHES = 20  # seconds between search requests
DELAY_BETWEEN_DOWNLOADS = 20  # seconds between image downloads
MAX_RETRIES = 2

def download_image(url, timeout=15):
    """Download image with proper headers and error handling"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
        'Accept-Language': 'sk-SK,sk;q=0.9,en;q=0.8',
        'Referer': 'https://duckduckgo.com/'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=timeout, stream=True)
        response.raise_for_status()
        
        # Check if content is actually an image
        content_type = response.headers.get('content-type', '')
        if not content_type.startswith('image/'):
            raise ValueError(f"Nie je obrázok: {content_type}")
            
        return response.content
    except requests.exceptions.RequestException as e:
        raise Exception(f"Chyba sťahovania: {e}")

def process_image(image_data):
    """Process image: convert to grayscale, pad, enhance contrast"""
    try:
        image = Image.open(io.BytesIO(image_data))
        
        # konverzia do grayscale
        image = image.convert("L")

        # orezanie alebo doplnenie okrajov na štvorcový formát
        image = ImageOps.pad(image, TARGET_SIZE, color=255)

        # zvýšenie kontrastu
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.5)
        
        return image
    except Exception as e:
        raise Exception(f"Chyba spracovania obrázka: {e}")

def search_with_retry(query, max_results, retries=2):
    """Search with retry logic"""
    for attempt in range(retries):
        try:
            ddgs = DDGS()
            results = list(ddgs.images(query, max_results=max_results))
            return results
        except Exception as e:
            if attempt < retries - 1:
                wait_time = (attempt + 1) * 5  # Increasing wait time
                print(f"  ⚠️ Chyba vyhľadávania, opakujem za {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise e

# Zoznam už spracovaných priečinkov pre lepšie hlásenie
folders = [f for f in os.listdir(dataset_dir) if os.path.isdir(os.path.join(dataset_dir, f))]
total_folders = len(folders)

print(f"🎬 Spúšťam sťahovanie obrázkov pre {total_folders} priečinkov...")

for current_index, folder in enumerate(folders, 1):
    folder_path = os.path.join(dataset_dir, folder)
    dataset_file = os.path.join(folder_path, "dataset.txt")

    if not os.path.isfile(dataset_file):
        print(f"❌ Chýba dataset.txt v {folder}, preskakujem...")
        continue

    # ak priečinok už obsahuje obrázky, preskočíme
    existing_images = [f for f in os.listdir(folder_path) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    if len(existing_images) >= num_images:
        print(f"⏩ [{current_index}/{total_folders}] Preskakujem {folder} (obrázky už existujú)")
        continue

    # načítanie názvu lieku
    with open(dataset_file, "r", encoding="utf-8") as f:
        nazov_lieku = f.readline().strip()

    print(f"🔍 [{current_index}/{total_folders}] Hľadám obrázky pre: '{nazov_lieku}'")

    # Rate limiting between searches
    if current_index > 1:
        delay = DELAY_BETWEEN_SEARCHES + random.uniform(0.5, 1.5)
        print(f"⏳ Čakám {delay:.1f}s pred vyhľadávaním...")
        time.sleep(delay)

    try:
        # vyhľadanie obrázkov cez DuckDuckGo s väčším počtom výsledkov
        results = search_with_retry(nazov_lieku, max_results=num_images + 2)
        
        if not results:
            print(f"  ❌ Pre '{nazov_lieku}' sa nenašli žiadne obrázky")
            continue
            
    except Exception as e:
        print(f"  ❌ Chyba pri vyhľadávaní: {e}")
        continue

    downloaded_count = 0
    successful_count = 0
    
    for i, result in enumerate(results):
        if successful_count >= num_images:
            break
            
        image_url = result.get("image")
        if not image_url:
            continue

        image_path = os.path.join(folder_path, f"image_{successful_count + 1}.png")
        downloaded_count += 1

        # Retry logic for failed downloads
        for retry in range(MAX_RETRIES):
            try:
                if retry > 0:
                    wait_time = DELAY_BETWEEN_DOWNLOADS * (retry + 1)
                    print(f"  🔄 Opakujem pokus {retry + 1}/{MAX_RETRIES} pre obrázok {i + 1} (čakám {wait_time}s)")
                    time.sleep(wait_time)

                print(f"  📥 Sťahujem obrázok {i + 1} z {len(results)}...")
                image_data = download_image(image_url)
                image = process_image(image_data)
                
                # uloženie vo formáte PNG
                image.save(image_path, format="PNG", optimize=True)
                successful_count += 1
                print(f"  ✅ Úspešne uložený obrázok {successful_count}/{num_images}")
                
                # Small delay between successful downloads
                if successful_count < num_images:
                    time.sleep(DELAY_BETWEEN_DOWNLOADS)
                    
                break  # Success, break retry loop
                
            except Exception as e:
                print(f"  ⚠️ Chyba pri obrázku {i + 1} (pokus {retry + 1}): {e}")
                if retry == MAX_RETRIES - 1:
                    print(f"  ❌ Preskakujem obrázok {i + 1}")

    # Summary for this folder
    if successful_count == 0:
        print(f"  ❌ Pre '{nazov_lieku}' sa nepodarilo stiahnuť žiadne obrázky")
    else:
        print(f"  📊 Pre '{nazov_lieku}' úspešne stiahnutých: {successful_count}/{num_images} obrázkov")

    # Final delay before next folder
    if current_index < total_folders:
        final_delay = DELAY_BETWEEN_SEARCHES + random.uniform(0.5, 1.0)
        print(f"⏳ Čakám {final_delay:.1f}s pred ďalším priečinkom...")
        time.sleep(final_delay)

print(f"\n🎉 Hotovo! Spracovaných {total_folders} priečinkov.")
print("Obrázky sú uložené a pripravené na OCR tréning.")