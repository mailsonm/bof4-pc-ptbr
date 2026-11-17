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
  --add-data "translation_data.pkg;." ^
  gui_patcher.py
```

#### On Linux / Steam Deck:
```bash
pyinstaller --noconfirm --clean --onefile --windowed \
  --name "BreathOfFireIV_PTBR_Patcher-Linux" \
  --add-data "translation_data.pkg:." \
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
python3 -m unittest patcher/test_patcher.py -v
```

---

## 📁 Repository Structure

```text
bof4-pc-ptbr/
├── .github/workflows/
│   └── build.yml               # Automated GitHub Actions CI workflow
├── patcher/
│   ├── patcher.py              # Core DAT injection and pointer calculation engine
│   ├── gui_patcher.py          # Tkinter graphical user interface
│   ├── translation_data.pkg    # Compressed translation dictionary (424 KB)
│   └── test_patcher.py         # Patcher test suite
├── save_editor/
│   ├── bof4_save/              # Save file parser & 8-bit XOR checksum engine
│   ├── gui/                    # Save Editor Tkinter interface
│   ├── run_gui.py              # Save Editor GUI entry point
│   ├── cli.py                  # Command-line interface
│   └── tests/                  # Save Editor test suite
├── tools/
│   └── port_translation.py     # Reverse engineering & PS1-to-PC extraction script
└── README.md                   # This documentation
```

---

## 🇧🇷 Português (PT-BR)

### Sobre o Projeto
Este repositório contém as ferramentas completas e de código aberto utilizadas para a tradução em Português do Brasil e edição de saves de **Breath of Fire IV (PC)** (GOG e Steam):

1. **Patcher de Tradução (`patcher/`):** Utilitário gráfico que injeta mais de 370 mapas de diálogos e o catálogo `INIT.DAT`, recalculando tabelas de ponteiros com segurança e criando backup automático em `DAT_BACKUP_EN`.
2. **Editor de Saves (`save_editor/`):** Utilitário gráfico para editar Zenny, pontos de pesca, atributos dos personagens e inventário, com recálculo automático de checksum 8-bit XOR.
3. **Compilação Aberta:** Ambos os programas podem ser executados diretamente em Python ou compilados via PyInstaller seguindo os comandos da seção [Building from Source](#-how-to-build-from-source-step-by-step).

---

## 🇪🇸 Español

### Sobre el Proyecto
Este repositorio contiene el código fuente abierto de las herramientas de traducción al portugués brasileño y editor de partidas guardadas para **Breath of Fire IV (PC)** (GOG y Steam):
- **Parcheador (`patcher/`):** Inserta los textos traducidos en los archivos `.DAT` del juego y recalcula los punteros binarios con copia de seguridad automática.
- **Editor de Partidas (`save_editor/`):** Modifica Zenny, pesca y atributos con recálculo automático de checksum 8-bit XOR.
- **Transparencia:** Todo el código es auditable y reproducible mediante PyInstaller.

---

## 🎖️ Credits & Acknowledgements

- **Original PS1 Translation:** **nhojunior** and the original localization team (v1.1a).
- **Reverse Engineering, PC Port & Tooling:** **Mailson Maia Alves** ([mailsonm](https://github.com/mailsonm)).
- **Original Game & Publishing:** **CAPCOM Co., Ltd.** & **GOG.com**.
- **Community:** Breath of Fire fans & Nexus Mods.

---

## 📄 License
This project is licensed under the [MIT License](LICENSE). Game assets, names, and trademarks belong to their respective copyright holders (CAPCOM Co., Ltd.).
