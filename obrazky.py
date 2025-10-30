#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Robust image fetcher for OCR dataset prep (NO PROCESSING).
- Sťahuje originálne obrázky (farby a rozlíšenie zachované).
- Náhodné malé pauzy, caching vyhľadávania, retries pri sťahovaní.
- Backend: Bing (ak je BING_IMAGE_SEARCH_KEY) alebo DuckDuckGo (ddgs).

Struktúra:
dataset/
  DrugA/
    dataset.txt   # 1. riadok: vyhľadávacia fráza (názov lieku)
  DrugB/
    dataset.txt
...

Výstup:
dataset/<drug>/image_1.jpg|png|webp ... image_N.ext
"""

import os
import io
import time
import json
import random
import traceback
import requests
from typing import List, Dict, Optional
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter, Retry

# ---------------- Optional Bing backend ----------------
BING_API_KEY = os.getenv("BING_IMAGE_SEARCH_KEY", "").strip()

# ---------------- DDG backend ----------------
try:
    from ddgs import DDGS    # pip install -U ddgs
except Exception:
    DDGS = None  # ok, ak chceš iba Bing

# Voliteľne: validácia, že bajty sú obrázok (neprepisujeme obsah)
try:
    from PIL import Image, ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False

# ============================ CONFIG ============================
DATASET_DIR = "dataset"
NUM_IMAGES = 3

SEARCH_BACKEND = "auto"  # 'auto'|'bing'|'ddg'

SEARCH_JITTER_SEC = (1.0, 3.0)   # wait medzi vyhľadávaniami
DOWNLOAD_JITTER_SEC = (0.8, 2.0) # wait medzi downloadmi

DDG_403_BEHAVIOR = "cooldown"    # 'cooldown' alebo 'skip'
COOLDOWN_WINDOW_SEC = (180, 420)

MAX_DOWNLOAD_ATTEMPTS = 3

CACHE_PATH = os.path.join(DATASET_DIR, "_search_cache.json")

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
]

MIN_BYTES, MAX_BYTES = 8 * 1024, 12 * 1024 * 1024  # 8KB – 12MB
# ================================================================

def polite_sleep(a: float, b: float) -> None:
    time.sleep(random.uniform(a, b))

def make_session() -> requests.Session:
    s = requests.Session()
    retries = Retry(
        total=5, connect=5, read=5,
        backoff_factor=1.2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
    )
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.headers.update({
        "User-Agent": random.choice(UA_POOL),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "sk-SK,sk;q=0.9,en;q=0.8",
    })
    return s

SESSION = make_session()

def load_cache() -> Dict[str, List[str]]:
    if not os.path.isfile(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}

def save_cache(cache: Dict[str, List[str]]) -> None:
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass

SEARCH_CACHE: Dict[str, List[str]] = load_cache()

def resolve_backend() -> str:
    if SEARCH_BACKEND == "auto":
        return "bing" if BING_API_KEY else "ddg"
    return SEARCH_BACKEND

# --------------------- Search backends -------------------------

def search_bing_images(query: str, want: int) -> List[str]:
    if not BING_API_KEY:
        raise RuntimeError("Bing API key missing. Set BING_IMAGE_SEARCH_KEY or use DDG.")
    url = "https://api.bing.microsoft.com/v7.0/images/search"
    params = {"q": query, "count": max(want + 6, want), "safeSearch": "Strict"}
    headers = {"Ocp-Apim-Subscription-Key": BING_API_KEY}
    r = requests.get(url, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()
    vals = data.get("value", [])
    urls = []
    for item in vals:
        u = item.get("contentUrl") or item.get("thumbnailUrl")
        if u:
            urls.append(u)
    # dedupe
    seen, uniq = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u); uniq.append(u)
    return uniq

_DDG_CLIENT: Optional[DDGS] = None

def ddg_client() -> DDGS:
    global _DDG_CLIENT
    if _DDG_CLIENT is None:
        if DDGS is None:
            raise RuntimeError("ddgs nie je nainštalované. pip install -U ddgs")
        _DDG_CLIENT = DDGS()
    return _DDG_CLIENT

def search_ddg_images(query: str, want: int) -> List[str]:
    client = ddg_client()
    try:
        results = list(client.images(query, region="sk-sk", safesearch="moderate", max_results=want + 10))
    except Exception as e:
        msg = str(e).lower()
        if "403" in msg or "i.js" in msg or "rate" in msg:
            if DDG_403_BEHAVIOR == "cooldown":
                cool = random.randint(*map(int, COOLDOWN_WINDOW_SEC))
                print(f"  🧊 DDG 403 – čakám {cool}s…")
                time.sleep(cool)
                try:
                    results = list(client.images(query, region="sk-sk", safesearch="moderate", max_results=want + 10))
                except Exception:
                    print("  ❌ Stále blokované – preskakujem.")
                    return []
            else:
                print("  🧊 DDG 403 – preskakujem.")
                return []
        else:
            print(f"  ❌ Chyba DDG: {e}")
            return []
    urls = []
    for r in results:
        img = r.get("image")
        if img: urls.append(img)
        thumb = r.get("thumbnail")
        if thumb: urls.append(thumb)
    seen, uniq = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u); uniq.append(u)
    return uniq

def search_images_cached(query: str, want: int) -> List[str]:
    backend = resolve_backend()
    key = f"{backend}::{query}::{want}"
    if key in SEARCH_CACHE and SEARCH_CACHE[key]:
        return SEARCH_CACHE[key][:]
    if backend == "bing":
        urls = search_bing_images(query, want)
    elif backend == "ddg":
        urls = search_ddg_images(query, want)
    else:
        raise RuntimeError(f"Unknown backend: {backend}")
    SEARCH_CACHE[key] = urls
    save_cache(SEARCH_CACHE)
    return urls[:]

# ---------------------- Download & Save ------------------------

def guess_ext_from_headers_or_url(content_type: str, url: str) -> str:
    ct = (content_type or "").lower()
    path = urlparse(url).path.lower()
    # map podľa Content-Type
    if "image/jpeg" in ct or path.endswith((".jpg", ".jpeg", ".jfif")):
        return ".jpg"
    if "image/png" in ct or path.endswith(".png"):
        return ".png"
    if "image/webp" in ct or path.endswith(".webp"):
        return ".webp"
    if "image/gif" in ct or path.endswith(".gif"):
        return ".gif"
    if "image/bmp" in ct or path.endswith(".bmp"):
        return ".bmp"
    if "image/tiff" in ct or path.endswith((".tif", ".tiff")):
        return ".tif"
    # default
    return ".jpg"

def download_image(url: str, timeout: int = 25) -> tuple[bytes, str]:
    last_exc = None
    for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
        try:
            r = SESSION.get(url, timeout=timeout, stream=True)
            if r.status_code == 429:
                pause = 10 * attempt
                print(f"    ⏳ 429 Too Many Requests — čakám {pause}s…")
                time.sleep(pause)
                continue
            if r.status_code >= 400:
                raise requests.HTTPError(f"HTTP {r.status_code} pre {url}")

            content_type = r.headers.get("content-type", "")
            data = r.content
            if len(data) < MIN_BYTES or len(data) > MAX_BYTES:
                raise ValueError("Veľkosť mimo limitu")

            # voliteľná validácia, že je to obrazok (bez zmeny dát)
            if HAVE_PIL:
                try:
                    im = Image.open(io.BytesIO(data))
                    im.verify()  # skontroluje integritu
                except Exception as e:
                    raise ValueError(f"Nie je validný obrázok: {e}")

            ext = guess_ext_from_headers_or_url(content_type, url)
            return data, ext
        except Exception as e:
            last_exc = e
            print(f"    ⚠️ Pokus {attempt}/{MAX_DOWNLOAD_ATTEMPTS} zlyhal: {e}")
            if attempt < MAX_DOWNLOAD_ATTEMPTS:
                time.sleep(1.5 * attempt)
    raise last_exc if last_exc else RuntimeError("Neznáma chyba sťahovania")

# ----------------------------- Main ---------------------------

def main() -> None:
    if not os.path.isdir(DATASET_DIR):
        raise SystemExit(f"Missing dataset directory: {DATASET_DIR}")

    folders = [f for f in os.listdir(DATASET_DIR)
               if os.path.isdir(os.path.join(DATASET_DIR, f))]
    total = len(folders)
    print(f"🎬 Sťahujem obrázky pre {total} priečinkov…")
    print(f"🔌 Backend: {resolve_backend().upper()}")

    for idx, folder in enumerate(sorted(folders), 1):
        folder_path = os.path.join(DATASET_DIR, folder)
        dataset_file = os.path.join(folder_path, "dataset.txt")

        if not os.path.isfile(dataset_file):
            print(f"❌ [{idx}/{total}] Chýba dataset.txt v “{folder}”, preskakujem…")
            continue

        # koľko už máme (image_*.ext)
        have = len([f for f in os.listdir(folder_path)
                    if f.lower().startswith("image_") and os.path.isfile(os.path.join(folder_path, f))])
        need = max(0, NUM_IMAGES - have)
        if need == 0:
            print(f"⏩ [{idx}/{total}] “{folder}”: už mám {have} obrázkov")
            continue

        with open(dataset_file, "r", encoding="utf-8") as fh:
            query = fh.readline().strip()

        print(f"🔍 [{idx}/{total}] Hľadám pre: “{query}” (chýba {need})")

        if idx > 1:
            polite_sleep(*SEARCH_JITTER_SEC)

        try:
            urls = search_images_cached(query, want=max(need, NUM_IMAGES) + 6)
        except Exception as e:
            print(f"  ❌ Chyba vyhľadávania: {e}")
            continue

        if not urls:
            print(f"  ❌ Nenašli sa URL pre “{query}”")
            continue

        saved = 0
        tried = 0
        for url in urls:
            if saved >= need:
                break
            tried += 1
            polite_sleep(*DOWNLOAD_JITTER_SEC)
            try:
                data, ext = download_image(url)
                out_path = os.path.join(folder_path, f"image_{have + saved + 1}{ext}")
                # ulož originálne bajty, žiadne spracovanie
                with open(out_path, "wb") as f:
                    f.write(data)
                saved += 1
                print(f"  ✅ {os.path.basename(out_path)} (z {tried} pokusov)")
            except Exception as e:
                print(f"  ⚠️ Zlyhané sťahovanie: {e}")

        if saved == 0:
            print(f"  ❌ Pre “{query}” sa nepodarilo uložiť žiadny obrázok")
        else:
            print(f"  📊 “{query}”: pridané {saved}/{need}")

    print("\n🎉 Hotovo. Obrázky uložené bez úprav (farba aj rozlíšenie zachované).")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️ Prerušené používateľom.")
    except Exception:
        print("❌ Neočakávaná chyba:")
        traceback.print_exc()
