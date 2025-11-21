import os

# Zoznam pôvodných názvov priečinkov (old names)
old_names = [
    "PARALEN 500 tbl 24x500 mg (blis.Al/PVC)",
    "MUCONASAL PLUS sol neb 1x10 ml",
    "FLECTOR RAPID 50 mg gra 21x50 mg (vre.papier/Al/PE)",
    "AGEN 5 tbl 30x5 mg",
    "NEBILET 5 mg tbl 28x5 mg",
    "CONCOR 5 tbl flm 30x5 mg",
    "MAGNOSOLV gra 30x6,1 g (sáčky)",
    "STILNOX 10 mg TBL FLM",
    "IBALGIN 400 tbl flm 48x400 mg (blis. PVC/Al)",
    "OLYNTH HA 0,1 % aer nao 1x10 ml",
    "BETALOC ZOK 50MG (blist.) tbl mod 28x50 mg",
    "NOVALGIN 500 mg tbl flm 20x500 mg",
    "BETALOC ZOK 25 mg (blist.) tbl mod 28x25 mg",
    "OTRIVIN MENTHOL 0,1% aer nao 1x10 ml (fľ.HDPE s dávkovačom)",
    "TEBOKAN 120 mg tbl flm 30x120 mg (blis.PVC/PVDC/Al)",
    "LAGOSA tbl obd 100",
    "FURON tbl 50x40 mg",
    "IBALGIN RAPIDCAPS 400 mg cps mol 30x400 mg (blis.PVC/PVDC/Al)",
    "VESSEL DUE F kapsuly cps 60x250 LSU (blis.PVC/PVDC/Al)",
    "SODIUM CHLORIDE 0,9%W/V I.V. INF inf 1x100 ml (sklo)",
    "NEUROL 0,5 mg tbl 30x0,5 mg (bli.)",
    "ASPIRIN PROTECT 100 tbl ent 50x100 mg",
    "OLYNTH 0,1 % aer nao 10 ml 0,1%",
    "ENELBIN 100 RETARD (FLAS.PE) tbl flm 100x100 mg",
    "PERINDOPRIL ARGININE 5 mg Servier tbl flm 30x5 mg",
    "CALCIUM CHLORATUM - IVAX sol por 100 ml",
    "BISOPROLOL-ratiopharm 5 mg tbl 30x5 mg",
    "ANOPYRIN 100 mg tbl 84x100 mg (blis.PVC/Al)",
    "ACYLPYRIN (blister) tbl 10x500 mg",
    "CORONAL 5 tbl flm 30x5 mg (PVC/PE/PVDC/Alu blis.)",
    "DEPAKINE CHRONO 500 mg tbl ret 30x500 mg",
    "MILURIT tbl 30x300 mg",
    "IMODIUM cps 20x2 mg",
    "UNIFLOX 0,3 % int opo/ots",
    "DICLOALGAN 25 mg mäkké kapsuly cps mol 20x25 mg (blis.PVC/PE/PVDC/Al)",
    "SUMAMED 500 mg tbl flm 3x500 mg",
    "Dorithricin pas ord 20",
    "Orinox 1 mg/ml aer nao 1x10 ml",
    "Lexaurin 3 mg tbl 28x3 mg (blis.Al/PVC)",
    "TRITACE 5 tbl 30x5 mg",
    "FENISTIL gtt 20 ml",
    "NASONEX aer nau 18 g (140 dávok)",
    "Amlodipin Stichting 5 mg tablety tbl 30x5 mg (bli.PVC/Al)",
    "NEUROL 0,25 tbl 30x0,25 mg (bli.)",
    "PRESTANCE 5 mg/5 mg tbl 30x5 mg/5 mg",
    "Magnesii lactas Galvex 500 mg",
    "DETRALEX tbl flm 180 (blis.Al/PVC)",
    "DETRALEX tbl flm 60",
    "PREDNISON 5 LÉČIVA tbl 20x5 mg",
    "PROTHAZIN tbl flm 20x25 mg"
]

# Zoznam nových názvov priečinkov (new names)
new_names = [
    "PARALEN 500",
    "MUCONASAL PLUS 1x10 ml",
    "FLECTOR RAPID 50 mg",
    "AGEN 5",
    "NEBILET 5 mg",
    "CONCOR 5",
    "MAGNOSOLV 30x6,1 g",
    "STILNOX 10 mg",
    "IBALGIN 400",
    "OLYNTH HA 0,1 %",
    "BETALOC ZOK 50MG",
    "NOVALGIN 500 mg",
    "BETALOC ZOK 25 mg",
    "OTRIVIN MENTHOL 0,1%",
    "TEBOKAN 120 mg",
    "LAGOSA 100",
    "FURON 50x40 mg",
    "IBALGIN RAPIDCAPS 400 mg",
    "VESSEL DUE F 60x250 LSU",
    "SODIUM CHLORIDE 0,9%W/V I.V. INF",
    "NEUROL 0,5 mg",
    "ASPIRIN PROTECT 100",
    "OLYNTH 0,1 %",
    "ENELBIN 100 RETARD",
    "PERINDOPRIL ARGININE 5 mg",
    "CALCIUM CHLORATUM - IVAX",
    "BISOPROLOL-ratiopharm 5 mg",
    "ANOPYRIN 100 mg",
    "ACYLPYRIN 500 mg",
    "CORONAL 5",
    "DEPAKINE CHRONO 500 mg",
    "MILURIT 30x300 mg",
    "IMODIUM 2 mg",
    "UNIFLOX 0,3 %",
    "DICLOALGAN 25 mg",
    "SUMAMED 500 mg",
    "DORITHRICIN pas ord",
    "ORINOX 1 mg/ml",
    "LEXAURIN 3 mg",
    "TRITACE 5",
    "FENISTIL gtt",
    "NASONEX 18 g",
    "AMLODIPIN STICHTING 5 mg",
    "NEUROL 0,25 mg",
    "PRESTANCE 5 mg/5 mg",
    "MAGNESII LACTAS GALVEX 500 mg",
    "DETRALEX 180",
    "DETRALEX 60",
    "PREDNISON 5 LÉČIVA 5 mg",
    "PROTHAZIN 25 mg"
]

# Cesta k priečinkom
base_folder = "C:/Users/fedor/Documents/GitHub/bakalarska_praca/dataset"

# Prejdeme všetkými priečinkami v "dataset" priečinku
def rename_drug_folders(base_folder):
    not_renamed = []  # Zoznam priečinkov, ktoré neboli premenované
    for drug_folder_name in os.listdir(base_folder):
        drug_folder_path = os.path.join(base_folder, drug_folder_name)
        
        # Skontrolujeme, či ide o priečinok
        if os.path.isdir(drug_folder_path):
            if drug_folder_name in old_names:
                # Získame index v zozname
                index = old_names.index(drug_folder_name)
                new_name = new_names[index]
                
                # Vytvoríme novú cestu pre priečinok
                new_folder_path = os.path.join(base_folder, new_name)
                
                # Premenujeme priečinok
                os.rename(drug_folder_path, new_folder_path)
                print(f"Premenovaný priečinok: {drug_folder_name} na {new_name}")
            else:
                not_renamed.append(drug_folder_name)

    return not_renamed

# Zavoláme funkciu na premenu priečinkov
not_renamed = rename_drug_folders(base_folder)

# Výpis priečinkov, ktoré neboli premenované
print("\nPriečinky, ktoré neboli premenované:")
for folder in not_renamed:
    print(folder)
