import pandas as pd

def process_excel_to_txt(input_file, output_file):
    try:
        # Načítanie druhého sheetu "Data"
        print("Načítavam dáta z XLSX súboru...")
        df = pd.read_excel(input_file, sheet_name='Data')
        
        # Zobrazenie presných názvov stĺpcov pre kontrolu
        print("Presné názvy stĺpcov:")
        for i, col in enumerate(df.columns):
            print(f"  {i}: '{col}'")
        
        # Použime presné názvy stĺpcov s medzerami
        required_columns = ['LIEK_popis ', 'ATC7_popis']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            print(f"Chyba: Chýbajúce stĺpce: {missing_columns}")
            return
        
        # Výber prvých 60 záznamov
        df_first_60 = df.head(60)
        
        print(f"Načítaných {len(df_first_60)} záznamov z celkových {len(df)}")
        
        # Vytvorenie TXT súboru s formátom pod seba
        with open(output_file, 'w', encoding='utf-8') as f:
            for index, row in df_first_60.iterrows():
                f.write(f"{row['LIEK_popis ']}\n")  # Pozor: medzera na konci!
                f.write(f"{row['ATC7_popis']}\n")
                f.write("\n")  # Prázdny riadok pre oddelenie záznamov
        
        print(f"✅ TXT súbor {output_file} bol úspešne vytvorený!")
        print(f"📊 Počet spracovaných záznamov: {len(df_first_60)}")
        
        # Zobrazenie prvých pár záznamov pre kontrolu
        print("\n📋 Ukážka prvých 3 záznamov:")
        for i in range(min(3, len(df_first_60))):
            print(f"Záznam {i+1}:")
            print(f"  LIEK_popis: '{df_first_60.iloc[i]['LIEK_popis ']}'")
            print(f"  ATC7_popis: '{df_first_60.iloc[i]['ATC7_popis']}'")
            print()
            
    except FileNotFoundError:
        print(f"❌ Chyba: Súbor {input_file} nebol nájdený.")
    except Exception as e:
        print(f"❌ Chyba: {e}")

# Hlavný program
if __name__ == "__main__":
    # Nastavenie názvov súborov
    input_filename = 'data.xlsx'  # Nahraď názvom svojho XLSX súboru
    output_filename = 'vystup.txt'
    
    # Spustenie spracovania
    process_excel_to_txt(input_filename, output_filename)