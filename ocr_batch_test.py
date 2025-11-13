# -*- coding: utf-8 -*-
"""
OCR tester (brand-only, v3)
- Zamerané len na názov lieku (brand) veľkým písmom na krabičke.
- OpenCV predspracovanie: CLAHE, adaptive threshold, zväčšenie, rotácie.
- Tesseract: PSM 7/6/11, whitelist A-Z0-9, user-words so všetkými brandmi.
- Výstup: ocr_results.csv (folder, image, expected_brand, ocr_text, score, status, variant).

Závislosti:
  pip install pillow pytesseract rapidfuzz unidecode opencv-python
+ Tesseract OCR (eng + slk)
"""

import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


import os, csv, json, re, sys, tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import pytesseract
from rapidfuzz.fuzz import partial_ratio, token_set_ratio
from unidecode import unidecode

# Ak Tesseract nie je v PATH, odkomentuj a nastav cestu:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

DATASET_ROOT = Path("dataset")
OUT_CSV = Path("ocr_results.csv")
IMAGE_GLOBS = ["*.jpg", "*.jpeg", "*.png", "*.webp"]

OEM = 1
PSM_LIST = [7, 6, 11]  # single line, block, sparse
WHITELIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-+"

# ---------- helpers ----------
def normalize(s: str) -> str:
    s = unidecode(s or "").lower()
    s = re.sub(r"[^a-z0-9 %/.\-x+]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def approx_score(a: str, b: str) -> int:
    if not a or not b:
        return 0
    return max(partial_ratio(a, b), token_set_ratio(a, b))

def extract_brand(name: str) -> str:
    """Z 'PARALEN 500 tbl 24x500 mg (…)' -> 'PARALEN' (aj 2-slovné značky ponecháme)."""
    if not name:
        return ""
    # odrež zátvorky a všetko od prvého čísla
    name = re.split(r"\(|\d", name)[0]
    # ponechaj prvé 1-2 slová
    words = [w for w in name.strip().split() if w]
    brand = " ".join(words[:2]) if words else ""
    brand = unidecode(brand).upper()
    # skráť na písmená/medzeru/hyphen
    brand = re.sub(r"[^A-Z \-]", "", brand).strip()
    return brand

def list_drug_folders(root: Path):
    out = []
    if not root.exists():
        return out
    for p in root.iterdir():
        if p.is_dir() and ((p/"interactions.json").exists() or (p/"dataset.txt").exists()):
            out.append(p)
    return sorted(out, key=lambda x: x.name.lower())

def read_drug_name(folder: Path) -> str:
    inter = folder / "interactions.json"
    if inter.exists():
        try:
            data = json.loads(inter.read_text(encoding="utf-8"))
            dn = data.get("drug_name") or ""
            if dn:
                return dn
        except Exception:
            pass
    ds = folder / "dataset.txt"
    if ds.exists():
        try:
            lines = [l.strip() for l in ds.read_text(encoding="utf-8", errors="ignore").splitlines() if l.strip()]
            if lines:
                return lines[0]
        except Exception:
            pass
    return folder.name

def find_images(folder: Path):
    imgs = []
    for g in IMAGE_GLOBS:
        imgs.extend(folder.glob(g))
    return [p for p in imgs if p.suffix.lower() in {".jpg",".jpeg",".png",".webp"}]

def cv2_imread_rgb(path: Path):
    img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB) if img is not None else None

def enhance_for_text(rgb: np.ndarray) -> np.ndarray:
    # upscale 2x
    rgb = cv2.resize(rgb, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    l2 = clahe.apply(l)
    lab2 = cv2.merge([l2, a, b])
    rgb2 = cv2.cvtColor(lab2, cv2.COLOR_LAB2RGB)
    gray = cv2.cvtColor(rgb2, cv2.COLOR_RGB2GRAY)
    gray = cv2.medianBlur(gray, 3)
    # adaptive threshold (text býva tmavý na svetlom)
    thr = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY, 31, 15)
    return thr

def central_roi(img: np.ndarray, band=0.45) -> np.ndarray:
    """vezmi stredný horizontálny pás, kde zvyčajne býva veľký brand"""
    h, w = img.shape[:2]
    ch = int(h*band)
    y1 = (h - ch)//2
    y2 = y1 + ch
    return img[y1:y2, :]

def tesseract_configs(expected_brand: str, user_words_file: Path|None):
    cfgs = []
    base = f'--oem {OEM} -c tessedit_char_whitelist={WHITELIST}'
    if user_words_file:
        base += f' --user-words "{user_words_file}"'
    for psm in PSM_LIST:
        cfgs.append((psm, f'{base} --psm {psm}'))
    # posledný pokus bez whitelistu, keby to bolo prehnané
    cfgs.append(("fallback6", f'--oem {OEM} --psm 6'))
    return cfgs

def ocr_text(pil_img: Image.Image, cfg: str) -> str:
    return pytesseract.image_to_string(pil_img, lang="eng+slk", config=cfg)

# ---------- main ----------
def main():
    if not DATASET_ROOT.exists():
        print(f"❌ '{DATASET_ROOT}' neexistuje")
        sys.exit(1)

    folders = list_drug_folders(DATASET_ROOT)
    if not folders:
        print("❌ Nenašli sa priečinky s dataset.txt/interactions.json.")
        sys.exit(2)

    # priprav user-words so všetkými brandmi (bias pre Tesseract)
    brands = []
    for f in folders:
        dn = read_drug_name(f)
        br = extract_brand(dn)
        if br:
            brands.append(br)
    brands = sorted(set(brands))
    tmp_words = None
    if brands:
        tmp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".words")
        for b in brands:
            # zapíš uppercase aj lowercase variant
            tmp.write(b+"\n")
            tmp.write(b.title()+"\n")
            tmp.write(b.lower()+"\n")
        tmp.close()
        tmp_words = Path(tmp.name)

    results = []

    for folder in folders:
        drug_name = read_drug_name(folder)
        expected_brand = extract_brand(drug_name)

        images = find_images(folder)
        for img_path in images:
            rgb = cv2_imread_rgb(img_path)
            if rgb is None:
                results.append([folder.name, img_path.name, expected_brand, "<OPEN_ERROR>", 0, "ERROR", ""])
                continue

            thr = enhance_for_text(rgb)
            rois = [
                ("center", central_roi(thr, 0.45)),
                ("center_narrow", central_roi(thr, 0.30)),
                ("full", thr),
            ]

            best_text = ""
            best_score = -1
            best_variant = ""

            for roi_name, roi in rois:
                pil = Image.fromarray(roi)
                for psm, cfg in tesseract_configs(expected_brand, tmp_words):
                    txt = ocr_text(pil, cfg)
                    # vyber najdlhší token A-Z (brand štýl)
                    major = re.findall(r"[A-Z][A-Z\-]{3,}", unidecode(txt).upper())
                    candidate = " ".join(major) if major else txt
                    score = approx_score(normalize(candidate), normalize(expected_brand))
                    if score > best_score:
                        best_score = score
                        best_text = txt
                        best_variant = f"{roi_name}|psm={psm}"

            status = "OK" if best_score >= 70 else "MISMATCH"

            results.append([
                folder.name,
                img_path.name,
                expected_brand,
                best_text.strip().replace("\n", " ")[:300],
                round(best_score, 2),
                status,
                best_variant
            ])

    # ulož CSV
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["folder","image","expected_brand","ocr_excerpt","score_brand","status","variant"])
        w.writerows(results)

    total = len(results)
    oks = sum(1 for r in results if r[5] == "OK")
    print(f"✅ Spracovaných obrázkov: {total}, zhôd OK: {oks} ({oks/total*100:.1f}%)")
    print(f"📄 Výsledky: {OUT_CSV.resolve()}")

    # upratať dočasný user-words
    if tmp_words and tmp_words.exists():
        try:
            tmp_words.unlink()
        except Exception:
            pass

if __name__ == "__main__":
    main()
