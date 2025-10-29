#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Robust image fetcher for OCR dataset prep.

Features:
- Small randomized delays instead of large fixed sleeps
- Graceful handling of DuckDuckGo 403 rate limits (cooldown or skip)
- Search result caching so repeated runs don't keep hitting the search endpoint
- Single persistent requests.Session with retry/backoff for downloads
- Optional Bing Image Search backend (set env BING_IMAGE_SEARCH_KEY to use)
- Basic image preprocessing (grayscale, pad to square, contrast boost)

Folder structure expected:
dataset/
  DrugA/
    dataset.txt   # first line: search query (e.g., drug name)
  DrugB/
    dataset.txt
  ...

Outputs:
dataset/<drug>/image_1.png ... image_N.png
"""

import os
import io
import time
import json
import random
import traceback
import requests
from typing import List, Dict, Optional

# ---- Optional backend: Bing Image Search (set your key in the environment) ----
BING_API_KEY = os.getenv("BING_IMAGE_SEARCH_KEY", "").strip()

# ---- Third-party libs (install: pip install duckduckgo_search pillow requests) ----
try:
    from duckduckgo_search import DDGS
except Exception:
    DDGS = None  # If not installed and you only want Bing, that's OK.

from PIL import Image, ImageOps, ImageEnhance
from requests.adapters import HTTPAdapter, Retry


# ============================ CONFIG ===========================================
# Root folder with per-drug folders
DATASET_DIR = "dataset"

# Number of processed images to save per drug
NUM_IMAGES = 3

# Target image size (for OCR)
TARGET_SIZE = (512, 512)

# Backend preference: 'auto' | 'bing' | 'ddg'
# - 'auto': use Bing if BING_IMAGE_SEARCH_KEY is set, else DDG
# - 'bing': require Bing key
# - 'ddg': force DuckDuckGo (unofficial, risk of 403)
SEARCH_BACKEND = "auto"

# Jitter windows (seconds)
SEARCH_JITTER_SEC = (1.0, 3.0)       # delay between searches
DOWNLOAD_JITTER_SEC = (0.8, 2.0)     # delay between downloads

# If DDG returns 403, what to do:
# 'cooldown' -> sleep for COOLDOWN_WINDOW then continue
# 'skip'     -> skip this folder (faster runs; safer on shared IPs)
DDG_403_BEHAVIOR = "cooldown"  # 'cooldown' or 'skip'
COOLDOWN_WINDOW_SEC = (180, 420)  # 3–7 minutes randomized

# Max total attempts per image download (Session has its own inner retries too)
MAX_DOWNLOAD_ATTEMPTS = 3

# Cache
CACHE_PATH = os.path.join(DATASET_DIR, "_search_cache.json")

# User-Agent pool to randomize a bit
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
]
# ==============================================================================


def polite_sleep(a: float, b: float) -> None:
    time.sleep(random.uniform(a, b))


def make_session() -> requests.Session:
    s = requests.Session()
    retries = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=1.2,  # 0, 1.2, 2.4, 3.6, ...
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
    )
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.headers.update({
        "User-Agent": random.choice(UA_POOL),
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "sk-SK,sk;q=0.9,en;q=0.8",
        # No Referer set to avoid hotlink/fingerprint issues
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


# ----------------------- Backends: Bing & DDG ----------------------------------

def search_bing_images(query: str, want: int) -> List[str]:
    """Bing Image Search (official API). Requires BING_IMAGE_SEARCH_KEY env var."""
    if not BING_API_KEY:
        raise RuntimeError("Bing API key missing; set BING_IMAGE_SEARCH_KEY or change SEARCH_BACKEND.")
    url = "https://api.bing.microsoft.com/v7.0/images/search"
    params = {
        "q": query,
        "count": max(want + 4, want),  # request a bit more to have fallbacks
        "safeSearch": "Strict",
    }
    headers = {"Ocp-Apim-Subscription-Key": BING_API_KEY}
    r = requests.get(url, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()
    vals = data.get("value", [])
    urls = []
    for item in vals:
        # Try contentUrl primarily; as a fallback, hostPageUrl is the web page
        u = item.get("contentUrl")
        if u:
            urls.append(u)
    return urls


_DDG_CLIENT: Optional[DDGS] = None


def ddg_client() -> DDGS:
    global _DDG_CLIENT
    if _DDG_CLIENT is None:
        if DDGS is None:
            raise RuntimeError("duckduckgo_search is not installed. Install it or use Bing.")
        _DDG_CLIENT = DDGS()
    return _DDG_CLIENT


def search_ddg_images(query: str, want: int) -> List[str]:
    """DuckDuckGo via duckduckgo_search (unofficial; prone to 403 rate limiting)."""
    client = ddg_client()
    # duckduckgo_search internally calls /i.js. We’ll catch 403 in the exception string.
    try:
        results = list(client.images(keywords=query, max_results=want + 6))
    except Exception as e:
        msg = str(e).lower()
        if "403" in msg or "ratelimit" in msg or "i.js" in msg:
            # Handle rate limiting according to config
            if DDG_403_BEHAVIOR == "cooldown":
                cool = random.randint(*map(int, COOLDOWN_WINDOW_SEC))
                print(f"  🧊 DDG rate-limit detected (403). Cooling down for {cool}s…")
                time.sleep(cool)
                # Try exactly once more after cooldown
                try:
                    results = list(client.images(keywords=query, max_results=want + 6))
                except Exception:
                    print("  ❌ Still blocked after cooldown. Skipping this query.")
                    return []
            else:
                print("  🧊 DDG rate-limit detected (403). Skipping this query.")
                return []
        else:
            # Some other network/parser error
            print(f"  ❌ DuckDuckGo search error: {e}")
            return []

    urls = []
    for r in results:
        # Prefer 'image' URL; keep 'thumbnail' as fallback
        img = r.get("image")
        if img:
            urls.append(img)
        thumb = r.get("thumbnail")
        if thumb:
            urls.append(thumb)
    # Deduplicate while keeping order
    seen = set()
    uniq = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def search_images_cached(query: str, want: int) -> List[str]:
    """Unified cached search across backends."""
    backend = resolve_backend()
    cache_key = f"{backend}::{query}::{want}"
    if cache_key in SEARCH_CACHE and SEARCH_CACHE[cache_key]:
        return SEARCH_CACHE[cache_key][:]

    if backend == "bing":
        urls = search_bing_images(query, want)
    elif backend == "ddg":
        urls = search_ddg_images(query, want)
    else:
        raise RuntimeError(f"Unknown backend: {backend}")

    # store some extras for retries/fallbacks
    SEARCH_CACHE[cache_key] = urls
    save_cache(SEARCH_CACHE)
    return urls[:]


# ----------------------- Download & Process ------------------------------------

def download_image(url: str, timeout: int = 25) -> bytes:
    """Download image bytes with session-level retries and basic checks."""
    last_exc = None
    for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
        try:
            r = SESSION.get(url, timeout=timeout, stream=True)
            if r.status_code == 429:
                # Short pause, then retry
                pause = 10 * attempt
                print(f"    ⏳ 429 Too Many Requests. Waiting {pause}s before retry…")
                time.sleep(pause)
                continue
            if r.status_code >= 400:
                raise requests.HTTPError(f"HTTP {r.status_code} for {url}")

            ct = r.headers.get("content-type", "")
            if not ct.startswith("image/"):
                # Some hosts mislabel; allow octet-stream if bytes sniff succeed
                if ct and "octet-stream" not in ct:
                    raise ValueError(f"Not an image: {ct}")
            return r.content
        except Exception as e:
            last_exc = e
            print(f"    ⚠️ Download attempt {attempt}/{MAX_DOWNLOAD_ATTEMPTS} failed: {e}")
            if attempt < MAX_DOWNLOAD_ATTEMPTS:
                time.sleep(1.5 * attempt)
    # All attempts failed
    raise last_exc if last_exc else RuntimeError("Unknown download error")


def process_image(image_data: bytes) -> Image.Image:
    """Convert to grayscale, pad to square TARGET_SIZE, boost contrast."""
    image = Image.open(io.BytesIO(image_data)).convert("L")
    image = ImageOps.pad(image, TARGET_SIZE, color=255)
    image = ImageEnhance.Contrast(image).enhance(1.5)
    return image


# ----------------------------- Main -------------------------------------------

def main() -> None:
    if not os.path.isdir(DATASET_DIR):
        raise SystemExit(f"Missing dataset directory: {DATASET_DIR}")

    folders = [f for f in os.listdir(DATASET_DIR)
               if os.path.isdir(os.path.join(DATASET_DIR, f))]
    total = len(folders)
    print(f"🎬 Spúšťam sťahovanie obrázkov pre {total} priečinkov…")
    print(f"🔌 Backend: {resolve_backend().upper()}")

    for idx, folder in enumerate(sorted(folders), 1):
        folder_path = os.path.join(DATASET_DIR, folder)
        dataset_file = os.path.join(folder_path, "dataset.txt")

        if not os.path.isfile(dataset_file):
            print(f"❌ [{idx}/{total}] Chýba dataset.txt v “{folder}”, preskakujem…")
            continue

        # Skip if we already have enough images
        existing = [f for f in os.listdir(folder_path)
                    if f.lower().endswith((".jpg", ".jpeg", ".png"))]
        if len(existing) >= NUM_IMAGES:
            print(f"⏩ [{idx}/{total}] Preskakujem “{folder}” (už mám {len(existing)} obrázkov)")
            continue

        with open(dataset_file, "r", encoding="utf-8") as fh:
            query = fh.readline().strip()

        print(f"🔍 [{idx}/{total}] Hľadám obrázky pre: “{query}”")

        # Small polite delay between searches
        if idx > 1:
            polite_sleep(*SEARCH_JITTER_SEC)

        try:
            urls = search_images_cached(query, want=NUM_IMAGES)
        except Exception as e:
            print(f"  ❌ Chyba vyhľadávania: {e}")
            continue

        if not urls:
            print(f"  ❌ Nenašli sa žiadne URL pre “{query}”")
            continue

        success = 0
        tried = 0

        for url in urls:
            if success >= NUM_IMAGES:
                break
            tried += 1

            # Small delay to avoid hammering hosts
            polite_sleep(*DOWNLOAD_JITTER_SEC)

            try:
                data = download_image(url)
                img = process_image(data)
                out_path = os.path.join(folder_path, f"image_{success + 1}.png")
                img.save(out_path, format="PNG", optimize=True)
                success += 1
                print(f"  ✅ Uložené: {success}/{NUM_IMAGES} (z {tried} pokusov)")
            except Exception as e:
                # Try to fall back to the next URL (thumbnails are included in cache list)
                print(f"  ⚠️ Zlyhané sťahovanie: {e}")

        if success == 0:
            print(f"  ❌ Pre “{query}” sa nepodarilo stiahnuť žiadne obrázky")
        else:
            print(f"  📊 “{query}”: úspešne {success}/{NUM_IMAGES}")

    print("\n🎉 Hotovo! Obrázky sú uložené a pripravené na OCR tréning.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️ Prerušené používateľom.")
    except Exception:
        print("❌ Neočakávaná chyba:")
        traceback.print_exc()
