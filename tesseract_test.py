import pytesseract
from PIL import Image, ImageOps

# ak treba, odkomentuj a nastav cestu k Tesseractu:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

IMG = r"dataset\ACYLPYRIN (blister) tbl 10x500 mg\image_1.jpg"  # ← tvoja cesta

img = Image.open(IMG)
img = ImageOps.grayscale(img).resize((img.width*2, img.height*2))  # zväčšenie pomáha
text = pytesseract.image_to_string(img, lang="eng+slk", config="--oem 1 --psm 6")

print("=== OCR TEXT ===")
print(text)

# jednoduchá kontrola zhody na ACYLPYRIN
norm = text.lower()
ok = any(k in norm for k in [
    "acylpyrin", "acy lpyrin", "acidum acetylsalicylicum", "acetylsalicyl"
]) and ("500 mg" in norm or "10" in norm)
print("\nMATCH:", "OK" if ok else "MISMATCH")
