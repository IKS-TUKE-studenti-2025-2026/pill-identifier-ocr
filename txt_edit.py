from PIL import Image
import pytesseract

# Na Windows zadaj cestu k tesseract.exe, ak je to potrebné
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Načítaj obrázok
image = Image.open('tvoj_obrazok.png')

# Extrahuj text
text = pytesseract.image_to_string(image)

print(text)
