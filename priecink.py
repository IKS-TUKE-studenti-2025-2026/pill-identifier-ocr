import os

# cesta k vstupnému TXT súboru
input_file = "vystup.txt"

# priečinok, kde sa majú vytvoriť priečinky liekov
output_folder = "dataset"

# vytvoríme výstupný priečinok, ak ešte neexistuje
os.makedirs(output_folder, exist_ok=True)

with open(input_file, "r", encoding="utf-8") as f:
    # načítame riadky, ošetríme prázdne riadky
    lines = [line.strip() for line in f.readlines() if line.strip()]

# spracovanie po dvojiciach (názov + účinná látka)
for i in range(0, len(lines), 2):
    if i + 1 < len(lines):
        nazov = lines[i]
        latka = lines[i + 1]

        # odstránenie zakázaných znakov vo Windows
        safe_name = "".join(c for c in nazov if c not in r'<>:"/\|?*')

        # vytvoríme priečinok pre liek
        liek_folder = os.path.join(output_folder, safe_name)
        os.makedirs(liek_folder, exist_ok=True)

        # uložíme názov aj účinnú látku do dataset.txt
        with open(os.path.join(liek_folder, "dataset.txt"), "w", encoding="utf-8") as out:
            out.write(f"{nazov}\n{latka}\n")

print("✅ Hotovo! Skontroluj priečinok:", output_folder)
