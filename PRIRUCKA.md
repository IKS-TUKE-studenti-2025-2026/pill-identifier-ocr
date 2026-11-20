# Príručka k projektu – rozpoznávanie liekov z fotky (OCR)

Projekt rozpozná liek z fotky obalu pomocou OCR (EasyOCR) a lokálneho jazykového modelu **gemma3:4b** (cez Ollama). Rozpoznaný text porovná so zoznamom liekov, na jednej fotke vie nájsť aj viac liekov a zobrazí informácie o lieku (kontraindikácie, varovania, interakcie) z openFDA. Gemma navyše urobí slovenské zhrnutie letáku, odpovedá na otázky k lieku a posudzuje interakcie medzi liekmi.

## Ako to spolu súvisí (pipeline)

```
data.xlsx ──(výber liekov)──► vystup.txt
                                  │
                   priecink.py    ▼
                          dataset/<liek>/dataset.txt
                                  │
   obrazky.py ───────────────────►│ image_1..3.jpg   (fotky obalov z innapternetu)
   fetch_openfda.py ─────────────►│ interactions.json (údaje z openFDA)
                                  │
   ocr_batch_test.py ◄────────────┤ (test presnosti OCR → ocr_results.csv)
                                  │
   migrate_dataset.py ────────────► app/dataset/<liek>/ (iba .txt + .json, bez fotiek)
                                  │
                                  ▼
                        app/app.py (Flask web aplikácia)
                          │        │
         recognition.py ◄─┘        └─► llm.py ──► Ollama (gemma3:4b)
         (fuzzy + gemma)
                          │
         evaluate.py ─────┘ (porovnanie metód na app/eval/images → vysledky.csv, suhrn.csv)
```

---

## Webová aplikácia – priečinok `app/`

| Súbor | Čo robí |
|---|---|
| `app/app.py` | **Hlavná aplikácia (Flask).** Na `/` prijme obrázok (upload, kamera alebo schránka), prečíta z neho text cez EasyOCR (`en`+`sk`, GPU) po odsekoch (každý môže byť z inej krabičky) a zavolá `recognition.identify_pills`. Pre nájdené lieky načíta `app/dataset/<liek>/interactions.json` a `dataset.txt`. Lieky, ktoré gemma našla, ale nie sú v zozname, dohľadá v openFDA podľa anglickej účinnej látky (`openfda.generic_name`). Keď gemma nebeží, skúsi openFDA podľa prvého slova z OCR (pôvodné správanie). Pri štarte na pozadí načíta model do pamäte (`llm.warmup`). Beží na `0.0.0.0:5000` v debug režime. |
| `app/app.py` – API pre gemmu | JSON endpointy, ktoré volá JavaScript po zobrazení výsledku: **`/api/summary`** (slovenské zhrnutie letáku, ukladá sa do `summary_sk.json`), **`/api/ask`** (otázka k lieku, max. 500 znakov), **`/api/interaction`** (interakcia dvoch liekov). Dáta liekov berie iba zo zoznamu alebo z `pill_cache` (naposledy zobrazené lieky), takže sa cez názov nedá dostať k iným súborom. Ak gemma nebeží, vracajú 503. |
| `app/recognition.py` | **Rozpoznanie lieku.** Postup: 1) fuzzy matching na celý text aj na každý odsek (verí sa mu od 85 %), 2) gemma priamo z fotky, 3) gemma z OCR textu (iba ak fotka nie je k dispozícii), 4) pôvodný fuzzy matching s hranicou 70 % ako posledná možnosť. Odpoveď gemmy sa vždy prevedie na presný názov zo zoznamu (`snap_to_list`) a liek sa prijme, iba ak má istotu ≥ 50 % a jeho názov sa naozaj nachádza v texte z krabičky alebo v OCR (poistka proti halucináciám). Vráti všetky nájdené lieky zoradené podľa istoty a zvlášť lieky mimo zoznamu. Hranice sú v konštantách `FUZZY_SURE`, `FUZZY_MIN`, `SNAP_MIN`, `GEMMA_MIN`. |
| `app/llm.py` | **Napojenie na gemma3:4b cez Ollama** (`http://localhost:11434`, teplota 0, kontext 8192, model ostáva v pamäti 30 min). Funkcie: `is_available`, `warmup`, `analyze_boxes` (lieky + údaje z krabičky: sila, forma, balenie, výrobca, účinná látka SK/EN, istota), `summarize`, `answer_question`, `check_interaction` (z letákov vyberie aj vety, ktoré priamo spomínajú druhú látku). Do modelu posiela sekcie letáku skrátené na 1500 znakov a prikazuje mu používať iba ten text. Pri chybe vráti `None`, takže aplikácia funguje aj bez Ollamy. |
| `app/evaluate.py` | **Experiment do bakalárky** – porovná 4 metódy rozpoznania (`fuzzy`, `ocr_gemma`, `vision_gemma`, `kombinacia`) na označených fotkách z `app/eval/`. Fotka je správne, iba ak metóda našla presne tie isté lieky. Meria aj čas (metódy s OCR platia aj čas OCR). Vyžaduje bežiacu Ollamu. Spustenie: `cd app && python evaluate.py`. |
| `app/eval/images/` | Testovacie fotky (jeden liek, dva lieky na jednej fotke, náhodný obrázok bez lieku). |
| `app/eval/labels.csv` | Správne odpovede: `subor,liek`; viac liekov sa oddeľuje `;`, prázdny stĺpec = na fotke nie je liek zo zoznamu. |
| `app/eval/vysledky.csv` | Výstup `evaluate.py` pre každú fotku a metódu (výsledok, správne/zle, čas). |
| `app/eval/suhrn.csv` | Výstup `evaluate.py` – presnosť a priemerný čas každej metódy. Posledný beh (5 fotiek): fuzzy 80 % / 0,4 s, ocr_gemma 80 % / 28,8 s, vision_gemma 100 % / 5,9 s, kombinácia 100 % / 18,6 s. |
| `app/templates/index.html` | Frontend (Bootstrap 5). Tri záložky: **Súbor**, **Kamera** (fotka cez `getUserMedia`), **Schránka** (Ctrl+V). Pre každý nájdený liek zobrazí kartu: názov, percento zhody, metódu rozpoznania, údaje z krabičky, rizikové stavy (`disease_flags`), **zhrnutie od gemmy**, poznámky a sekcie z openFDA v akordeóne. Na karte je formulár **„Opýtaj sa“** a **kontrola interakcie s iným liekom**. Ak je na fotke viac liekov, automaticky sa skontrolujú interakcie medzi nimi. Ukazuje, či gemma beží, upozornenie (disclaimer) a tlačidlo na surový OCR text. |
| `app/zoznam_liekov.txt` | Zoznam 100 názvov liekov (50 pôvodných + 50 ďalších najpredávanejších z `data.xlsx`, bez duplicitných značiek), voči ktorým sa porovnáva OCR text. Za `#` môže byť poznámka; 12 liekov, ktorých údaje sú zo SPC zo ŠÚKL (nie z openFDA), je označených `# SPC zo ŠÚKL (nie je v openFDA)`. Názvy sa musia zhodovať s názvami priečinkov v `app/dataset/`. |
| `app/dataset/<liek>/dataset.txt` | Popis lieku: 1. riadok celý názov balenia, 2. riadok účinná látka (SK), 3. riadok účinná látka (EN). |
| `app/dataset/<liek>/interactions.json` | Údaje z openFDA: `sections` (kontraindikácie, varovania, interakcie, nežiaduce účinky…), `disease_flags` (napr. astma, tehotenstvo), `matched_name`, `status`. |
| `app/dataset/<liek>/summary_sk.json` | **Cache slovenského zhrnutia od gemmy** (`na_co`, `davkovanie`, `kontraindikacie`, `varovania`, `interakcie`, `vedlajsie_ucinky`). Vytvorí ho `/api/summary` pri prvom zobrazení lieku, potom sa už iba načítava. Ak chceš zhrnutie vygenerovať znova (napr. po zmene promptu), súbor zmaž. Zatiaľ existuje pre AGEN 5, NOVALGIN 500 mg a PARALEN 500. |
| `app/uploads/` | Sem sa ukladajú nahrané obrázky (`input.jpg` = posledná fotka z kamery/schránky). Ide o dočasné súbory, ktoré netreba verzovať. |

**Spustenie:**
```bash
ollama pull gemma3:4b   # iba prvýkrát
ollama serve            # ak Ollama už nebeží ako služba
cd app
python app.py           # potom otvor http://localhost:5000
```
Bez Ollamy aplikácia beží tiež, ale iba s fuzzy matchingom (bez zhrnutia, otázok a kontroly interakcií).

---

## Dáta – koreňový priečinok

| Súbor | Čo obsahuje |
|---|---|
| `data.xlsx` | Zdrojová tabuľka výdaja liekov za SR (hárky `Metadata`, `Data`, `Struktura`; ~24 700 riadkov: ATC kód, názov lieku, výrobca, počet balení za obdobie 2025/04–06). Z nej sa vyberali lieky do datasetu. |
| `vystup.txt` | Vybrané lieky v trojiciach riadkov: celý názov balenia / účinná látka SK / účinná látka EN, trojice sú oddelené prázdnym riadkom. Je to vstup pre `priecink.py`. |
| `vycistene.txt` | Skrátené názvy liekov (bez veľkosti balenia) – pracovný medzikrok. |
| `zoznam_liekov.txt` | Finálny zoznam 100 liekov (rovnaký ako `app/zoznam_liekov.txt`); používa ho `ocr_batch_test.py`. |
| `dataset/<liek>/` | Plný dataset: `dataset.txt`, `interactions.json` a **fotky obalov** `image_1..3.jpg/png`. |
| `dataset/_lexicon.jsonl` | Zoznam priečinok → značka → účinná látka (vytvára `priecink.py`). |
| `dataset/_search_cache.json` | Cache výsledkov vyhľadávania obrázkov (vytvára `obrazky.py`), aby sa to isté nehľadalo znova. |
| `ocr_results.csv` | Výsledky posledného OCR testu: detekovaný text, odhadnutý liek, % zhody, či bol odhad správny, správny priečinok. |
| `requirements.txt` | Python závislosti (Flask, easyocr, opencv, fuzzywuzzy, pytesseract, ddgs, requests…). |

---

## Skripty na prípravu datasetu (v poradí použitia)

| Skript | Čo robí |
|---|---|
| `priecink.py` | Číta `vystup.txt` a pre každý liek vytvorí priečinok `dataset/<bezpečný_názov>/` s `dataset.txt`. Rieši zakázané znaky a názvy vo Windows, dĺžku a duplicity. Zapisuje aj `dataset/_lexicon.jsonl`. |
| `image_scraper.py` | Napriek názvu **nesťahuje obrázky**. Porovná `vystup.txt` s priečinkami v `dataset/` a z TXT vyhodí lieky, ktoré priečinok nemajú. Pred prepisom spraví zálohu `vystup.backup-<čas>.txt`. `DRY_RUN = True` iba vypíše, čo by zmenil. |
| `obrazky.py` | **Sťahuje fotky obalov** – pre každý priečinok v `dataset/` vyhľadá podľa 1. riadku `dataset.txt` obrázky (DuckDuckGo cez `ddgs`, alebo Bing, ak je nastavená premenná `BING_IMAGE_SEARCH_KEY`) a uloží 3 originály ako `image_N.ext`. Robí pauzy, opakuje neúspešné pokusy, cachuje výsledky a pri blokovaní (403) čaká. |
| `obrazky_oprava.py` | Kontrola obrázkov – zistí, ktoré fotky v datasete sú čiernobiele, a zapíše to do `grayscale_audit.csv`. |
| `dataset/čistič.py` | ⚠️ **Maže všetky obrázky** v priečinkoch liekov (a `_search_cache.json`). Slúži na čisté opätovné stiahnutie. Aktuálne je `DRY_RUN = False`, takže maže naostro. Spúšťa sa z koreňa projektu. |
| `fetch_openfda.py` | Pre každý liek vezme anglické názvy účinnej látky (3. riadok `dataset.txt`) a stiahne z openFDA (`api.fda.gov/drug/label.json`) sekcie príbalového letáku. Regexmi v nich hľadá rizikové stavy (astma, tehotenstvo, zlyhanie obličiek…) a všetko uloží do `interactions.json`. |
| `list_not_found.py` | Prehľad: vypíše lieky, pre ktoré openFDA nič nenašla (`status: not_found` alebo prázdne sekcie). |
| `migrate_dataset.py` | Skopíruje `dataset.txt` a `*.json` z `dataset/` do `app/dataset/` bez fotiek, aby bola aplikácia menšia. Cesty sú napevno nastavené na `C:\Users\fedor\...`. |

---

## OCR testy a experimenty

| Skript | Čo robí |
|---|---|
| `ocr_batch_test.py` | **Hlavný test presnosti.** Na všetky fotky v `dataset/` pustí EasyOCR (predspracovanie: odtiene šedej → CLAHE → 2× zväčšenie). Výsledok fuzzy porovná so `zoznam_liekov.txt` (partial ratio 70 % + token set 30 % + bonus za prvé slovo názvu). Zapíše `ocr_results.csv` a vypíše celkovú presnosť. Používa rovnaký matching ako `app.py`. |
| `tesseract_test2.py` | Staršia verzia testu: EasyOCR bez predspracovania, porovnáva s názvom priečinka. Tiež **prepisuje `ocr_results.csv`**. |
| `tesseract_test.py` | Test Tesseractu na jednom obrázku (ACYLPYRIN). Cesta k obrázku je už neplatná, keďže priečinok bol premenovaný. |
| `txt_edit.py` | Minimálna ukážka Tesseract OCR (`tvoj_obrazok.png`). Ide len o šablónu. |

---

## Ostatné

| Súbor | Poznámka |
|---|---|
| `rozvrhy.py` | **Nesúvisí s projektom** – kreslí graf rozvrhov kamarátov cez matplotlib. Nie je v gite (untracked). |
| `.gitignore` | Ignoruje `.venv/`, `__pycache__`, súbory IDE a OS. |
| `.gitattributes` | Normalizácia koncov riadkov. |
| `.venv/` | Virtuálne prostredie Pythonu (lokálne, nie je v gite). |

---

## Na čo si dať pozor

- **`requirements.txt` je uložený v kódovaní UTF-16** (vznikol cez `pip freeze > requirements.txt` v PowerShelli). `pip install -r` s ním môže zlyhať, preto ho treba preuložiť ako UTF-8.
- `ocr_batch_test.py` aj `tesseract_test2.py` zapisujú do toho istého `ocr_results.csv`, takže jeden prepíše výsledky druhého.
- `priecink.py` a `image_scraper.py` čítajú `vystup.txt` po **dvojiciach** riadkov, ale súbor má teraz **trojice** (pridaný EN názov). Pred ďalším spustením ich treba upraviť.
- Skripty v koreni používajú relatívnu cestu `dataset/`, takže ich treba spúšťať z koreňa projektu. `ocr_batch_test.py`, `tesseract_test2.py` a `migrate_dataset.py` majú absolútne cesty `C:\Users\fedor\...`.
- EasyOCR je nastavený s `gpu=True`. Bez CUDA GPU beží pomaly na CPU.
- Pre 50 nových liekov zatiaľ nie sú stiahnuté fotky obalov (`obrazky.py`), takže ich `ocr_batch_test.py` netestuje. 12 z nich openFDA nepozná (lieky predávané iba v EÚ). Ich `interactions.json` je vytvorený zo **slovenského SPC zo ŠÚKL** (`source: sukl_spc`, `language: sk`, odkaz v `spc_url`): kapitoly 4.1–4.9 sú uložené ako `indications_and_usage`, `dosage_and_administration`, `contraindications`, `warnings_and_cautions`, `drug_interactions`, `pregnancy_and_lactation`, `driving_and_machines`, `adverse_reactions`, `overdosage`. `disease_flags` sa hľadajú slovenskými regexmi. BILAHIST nie je v databáze ŠÚKL, použité je SPC Bilastin STADA 20 mg (rovnaká látka aj sila). Betahistin Mylan sa dnes volá Betahistin Viatris.
- Gemma (`gemma3:4b`) beží lokálne cez Ollamu a potrebuje približne 4 GB pamäte. Prvý dotaz po štarte môže trvať dlhšie, kým sa model načíta.
- Gemma z OCR textu (`ocr_gemma`) je pomalá a menej presná. Keď na obrázku nie je liek, často vypíše celý zoznam liekov, preto ju aplikácia používa iba vtedy, keď nemá fotku.
- `summary_sk.json` sa po zmene promptu v `llm.summarize` neprepíše sám, staré súbory treba zmazať.
- `evaluate.py` prepisuje `app/eval/vysledky.csv` a `suhrn.csv`. Testovacia sada má zatiaľ iba 5 fotiek, takže percentá sú len orientačné.
