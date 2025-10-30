# detect_grayscale.py
import os, csv
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True

DATASET_DIR = Path("dataset")
OUT_CSV = "grayscale_audit.csv"
IMG_EXTS = {".png",".jpg",".jpeg",".webp",".bmp",".tif",".tiff",".jfif"}

def is_image(p: Path):
    return p.is_file() and p.suffix.lower() in IMG_EXTS and p.name.lower() != "dataset.txt"

def is_grayscale(img: Image.Image) -> bool:
    im = ImageOps.exif_transpose(img).convert("RGB")
    arr = np.asarray(im, dtype=np.int16)
    r,g,b = arr[...,0], arr[...,1], arr[...,2]
    # priemerný rozdiel medzi kanálmi
    diff = (np.abs(r-g).mean() + np.abs(r-b).mean() + np.abs(g-b).mean())/3.0
    return diff < 1.5  # veľmi prísne; uprav ak treba

def main():
    rows = []
    for folder in sorted([d for d in DATASET_DIR.iterdir() if d.is_dir() and (d/"dataset.txt").exists()]):
        for p in sorted([x for x in folder.iterdir() if is_image(x)]):
            try:
                with Image.open(p) as im:
                    gray = is_grayscale(im)
                rows.append({"folder": folder.name, "file": p.name, "grayscale": gray})
            except Exception as e:
                rows.append({"folder": folder.name, "file": p.name, "grayscale": "ERROR: "+str(e)})
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["folder","file","grayscale"])
        w.writeheader(); w.writerows(rows)
    print(f"✅ Hotovo, pozri {OUT_CSV}")

if __name__ == "__main__":
    main()
