import os

# cesta k vstupnému TXT súboru
input_file = r"vystup.txt"

# priečinok, kde sa majú vytvoriť priečinky liekov
output_folder = r"dataset"

# vytvoríme výstupný priečinok, ak ešte neexistuje
os.makedirs(output_folder, exist_ok=True)

with open(input_file, "r", encoding="utf-8") as f:
    # odfiltrujeme prázdne riadky
    lines = [line.strip() for line in f.readlines() if line.strip()]

# spracovanie po trojiciach (názov, látka, látka_en)
for i in range(0, len(lines), 3):
    if i + 2 < len(lines):
        nazov = lines[i]
        latka = lines[i + 1]
        latka_en = lines[i + 2]

        # odstránenie zakázaných znakov vo Windows
        safe_name = "".join(c for c in nazov if c not in r'<>:"/\|?*')

        # vytvoríme priečinok
        liek_folder = os.path.join(output_folder, safe_name)
        os.makedirs(liek_folder, exist_ok=True)

        # uložíme názov + účinné látky do dataset.txt
        with open(os.path.join(liek_folder, "dataset.txt"), "w", encoding="utf-8") as out:
            out.write(f"{nazov}\n{latka}\n{latka_en}\n")

print("✅ Hotovo! Skontroluj priečinok:", output_folder)
