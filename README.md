# 🐉 Breath of Fire IV (PC) — Translation Patcher & Save Editor

[![Build Binaries](https://github.com/mailsonm/bof4-pc-ptbr/actions/workflows/build.yml/badge.svg)](https://github.com/mailsonm/bof4-pc-ptbr/actions/workflows/build.yml)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Nexus Mods - Translation](https://img.shields.io/badge/NexusMods-Mod%2010%20(PT--BR)-orange.svg)](https://www.nexusmods.com/breathoffire4/mods/10)
[![Nexus Mods - Save Editor](https://img.shields.io/badge/NexusMods-Mod%2011%20(Save%20Editor)-green.svg)](https://www.nexusmods.com/breathoffire4/mods/11)

Official open-source repository containing the translation patcher tools and standalone save file editor for **Breath of Fire IV** on PC (compatible with GOG and Steam releases).

---

## 🛡️ Nexus Mods Moderation & Security Verification

This section provides complete build instructions and transparency information for Nexus Mods staff and community reviewers.

- **Mod 10 (Translation Mod):** [Breath of Fire IV PT-BR](https://www.nexusmods.com/breathoffire4/mods/10)
  - Distributed binary: `BreathOfFireIV_PTBR_Patcher.exe` (Windows) / `BreathOfFireIV_PTBR_Patcher-Linux` (Linux/Steam Deck)
  - Source code: [`patcher/`](patcher/)
- **Mod 11 (Save Editor):** [Breath of Fire IV Save Editor](https://www.nexusmods.com/breathoffire4/mods/11)
  - Distributed binary: `BreathOfFireIVSaveEditor.exe` (Windows) / `BreathOfFireIVSaveEditor-Linux` (Linux/Steam Deck)
  - Source code: [`save_editor/`](save_editor/)

Both utilities are written in pure Python 3 with standard Tkinter UI and compiled into single-file standalone binaries using **PyInstaller**. Any antivirus warnings are generic heuristic false-positives triggered by standard PyInstaller unpacking bootloaders.

---

## 🔨 How to Build from Source (Step-by-Step)

The binaries distributed on Nexus Mods are 100% reproducible directly from this source code.

### 1. Prerequisites
- Python 3.10 or newer (tested on 3.10, 3.11, 3.12, and 3.14)
- Install PyInstaller:
  ```bash
  pip install --upgrade pip
  pip install pyinstaller
  ```

---

### 2. Building the Translation Patcher

Navigate to the `patcher/` directory:
```bash
cd patcher
```

#### On Windows:
```cmd
pyinstaller --noconfirm --clean --onefile --windowed ^
  --name "BreathOfFireIV_PTBR_Patcher" ^
  --add-data "translation_v2.pkg;." ^
  gui_patcher.py
```

#### On Linux / Steam Deck:
```bash
pyinstaller --noconfirm --clean --onefile --windowed \
  --name "BreathOfFireIV_PTBR_Patcher-Linux" \
  --add-data "translation_v2.pkg:." \
  gui_patcher.py
```

The resulting executable is generated in `patcher/dist/`.

---

### 3. Building the Save Editor

Navigate to the `save_editor/` directory:
```bash
cd save_editor
```

#### On Windows:
```cmd
pyinstaller --noconfirm --clean --onefile --windowed ^
  --name "BreathOfFireIVSaveEditor" ^
  run_gui.py
```

#### On Linux / Steam Deck:
```bash
pyinstaller --noconfirm --clean --onefile --windowed \
  --name "BreathOfFireIVSaveEditor-Linux" \
  run_gui.py
```

The resulting executable is generated in `save_editor/dist/`.

---

## 🚀 Running Directly from Source (No Compilation Needed)

You can run both utilities directly using Python without compiling:

```bash
# Clone the repository
git clone https://github.com/mailsonm/bof4-pc-ptbr.git
cd bof4-pc-ptbr

# Run Translation Patcher
python3 patcher/gui_patcher.py

# Run Save Editor
python3 save_editor/run_gui.py

# Run Unit Tests
python3 -m unittest discover -s save_editor/tests -v
python3 -m unittest discover -s tests -v
python3 -m unittest patcher/test_patcher.py -v
```

---

## ✨ What's New in v2.0.0 (Native PC Localization)

- **100% Native PC PT-BR Translation:** Re-translated completely from scratch directly from the clean PC English corpus (`7,402` strings across `305` `.DAT` files: all story dialogues, battle tutorials/hints, Bestiary/Peep descriptions, all `567` item/equipment/skill descriptions, Camp/Shop/Manillo/Fishing/Faerie/Save menus, and Chapter Titles).
- **Native Portuguese Accented Fonts & VWF:** Synthesized `26` crisp 4bpp accented glyphs (`á à â ã é ê í ó ô õ ú ç Á À Â Ã É Ê Í Ó Ô Õ Ú Ç º ª` at `0x88..0xA1`) in both `16×16` (`INIT.DAT[8]`) and `24×24` (`INIT.DAT[9]`), with exact VWF advance-width & left-bearing metrics patched into `BOF4.exe`.
- **Reversible `BOF4.exe` Micro-Patch:** Updates Title Menu (`NOVO JOGO`, `CARREGAR`, `OPÇÕES`), Minigame HUD (`MELHOR`, `NOVO RECORDE`), Compass (`L`/`O`), and VWF tables with valid PE CheckSum and automatic `BOF4.exe.bak` backup/restore.
- **English Proper Names Preserved:** Keeps original English names for items, consumables, fish, rods, lures, weapons, armor, accessories, key items (`INIT.DAT[7]` untouched), spells/skills/Wills, monsters, characters, and locations.

---

## 📁 Repository Structure

```text
bof4-pc-ptbr/
├── .github/workflows/
│   └── build.yml               # Automated GitHub Actions CI workflow
├── bof4_ptbr/
│   ├── GLOSSARY.md             # PT-BR localization glossary & style guide
│   ├── codec.py                # Control-code-aware text codec & VWF metrics
│   ├── validate.py             # VWF pixel-width & structural tag validator
│   ├── font_builder.py         # 16x16 / 24x24 4bpp PT-BR glyph synthesizer
│   ├── exe_patcher.py          # BOF4.exe VWF & UI micro-patcher + PE CheckSum
│   ├── dat_engine.py           # Strict (type_param, dest) .DAT parser/writer
│   ├── extract_corpus.py       # Deduplicated 8-shard corpus extractor
│   ├── build_patch.py          # v2.0.0 package compiler & CLI installer
│   └── corpus/                 # 8 validated PT-BR translation shards
├── patcher/
│   ├── patcher.py              # Standalone v2.0.0 DAT + EXE patcher & restorer
│   ├── gui_patcher.py          # Tkinter graphical user interface
│   ├── translation_v2.pkg      # Compressed v2.0.0 translation bundle (253 KB)
│   └── test_patcher.py         # Patcher test suite
├── save_editor/
│   ├── bof4_save/              # Save file parser & 8-bit XOR checksum engine
│   ├── gui/                    # Save Editor Tkinter interface
│   ├── run_gui.py              # Save Editor GUI entry point
│   ├── cli.py                  # Command-line interface
│   └── tests/                  # Save Editor test suite
├── tests/                      # Full codec, font, EXE & DAT engine test suite
└── README.md                   # This documentation
```

---

## 🇧🇷 Português (PT-BR)

### Sobre o Projeto (v2.0.0)
Este repositório contém o código-fonte completo e auditável da **tradução nativa v2.0.0 em Português do Brasil** e do editor de saves para **Breath of Fire IV (PC)** (GOG e Steam):

1. **Tradução Nativa Completa (`bof4_ptbr/`):** Todos os diálogos de história, menus, lojas, pesca, colônia das fadas, tutoriais de batalha e `567` descrições de itens/equipamentos/magias foram traduzidos do zero para o PC, preservando nomes originais em inglês de itens, equipamentos, magias, monstros e locais.
2. **Fontes Acentuadas & VWF:** Adição de `26` glifos nativos (`á à â ã é ê í ó ô õ ú ç Á À Â Ã É Ê Í Ó Ô Õ Ú Ç º ª`) em `16×16` e `24×24` (`INIT.DAT[8..9]`) e tabelas de largura variável (VWF) + menus do título no `BOF4.exe`, sem corromper retratos ou caixas de diálogo.
3. **Patcher v2.0.0 (`patcher/`):** Utilitário gráfico com backup automático em `DAT_BACKUP_EN/` e `BOF4.exe.bak` e restauração 1-clique para o inglês original.
4. **Editor de Saves (`save_editor/`):** Utilitário gráfico para editar Zenny, pontos de pesca, atributos e inventário com recálculo de checksum 8-bit XOR.
5. **Compilação Aberta:** Ambos os programas podem ser executados diretamente em Python ou compilados via PyInstaller seguindo os comandos da seção [Building from Source](#-how-to-build-from-source-step-by-step).

---

## 🇪🇸 Español

### Sobre el Proyecto (v2.0.0)
Este repositorio contiene el código fuente abierto de la **traducción nativa v2.0.0 al portugués brasileño** y editor de partidas guardadas para **Breath of Fire IV (PC)** (GOG y Steam):
- **Traducción Nativa (`bof4_ptbr/`):** Diálogos, menús, tutoriales y descripciones traducidos desde cero para PC con fuentes 4bpp acentuadas (`16×16` y `24×24`) y ajuste VWF en `BOF4.exe`.
- **Parcheador (`patcher/`):** Aplica los `.DAT` y el microparche reversible de `BOF4.exe` con copia de seguridad automática (`DAT_BACKUP_EN` y `BOF4.exe.bak`).
- **Editor de Partidas (`save_editor/`):** Modifica Zenny, pesca y atributos con recálculo automático de checksum 8-bit XOR.
- **Transparencia:** Todo el código es auditable y reproducible mediante PyInstaller.

---

## 🎖️ Credits & Acknowledgements

- **Native PC Reverse Engineering, From-Scratch PT-BR Localization, Font/EXE Patching, Patcher & Save Editor:** **Mailson Maia Alves** ([mailsonm](https://github.com/mailsonm)).
- **Original Game & Publishing:** **CAPCOM Co., Ltd.** & **GOG.com**.
- **Community:** Breath of Fire fans & Nexus Mods.

---

## 📄 License
This project is licensed under the [MIT License](LICENSE). Game assets, names, and trademarks belong to their respective copyright holders (CAPCOM Co., Ltd.).
