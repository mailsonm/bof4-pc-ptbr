# Breath of Fire IV (PC) — Translation Patcher & Save Editor

Open-source translation patcher and save file editor for Breath of Fire IV on PC (compatible with GOG and Steam releases).

## Overview

This repository contains the complete open-source tooling used for the Portuguese (PT-BR) localization patch and save file editing:

- **Patcher (`patcher/`)**: Standalone Python / Tkinter graphical tool that applies localized strings into game `DAT` archives and recalculates pointer tables.
- **Save Editor (`save_editor/`)**: Graphical and command-line utility for modifying Zenny, Fishing stats, character levels, and inventory with automatic 8-bit checksum calculation.
- **Tools (`tools/`)**: Extraction and format conversion utilities.

---

## Building from Source

The binaries distributed on Nexus Mods are compiled directly from this Python source code using PyInstaller.

### 1. Prerequisites

- Python 3.10+
- `pip install pyinstaller`

### 2. Build the Patcher Executable

#### Linux:
```bash
cd patcher
pyinstaller --noconfirm --clean --onefile --windowed \
  --name "BreathOfFireIV_PTBR_Patcher-Linux" \
  --add-data "translation_data.pkg:." \
  gui_patcher.py
```

#### Windows:
```cmd
cd patcher
pyinstaller --noconfirm --clean --onefile --windowed ^
  --name "BreathOfFireIV_PTBR_Patcher" ^
  --add-data "translation_data.pkg;." ^
  gui_patcher.py
```

The compiled binary will be placed inside `patcher/dist/`.

---

### 3. Build the Save Editor Executable

#### Linux:
```bash
cd save_editor
pyinstaller --noconfirm --clean --onefile --windowed \
  --name "BreathOfFireIVSaveEditor-Linux" \
  run_gui.py
```

#### Windows:
```cmd
cd save_editor
pyinstaller --noconfirm --clean --onefile --windowed ^
  --name "BreathOfFireIVSaveEditor" ^
  run_gui.py
```

The compiled binary will be placed inside `save_editor/dist/`.

---

## Running from Source (No Compilation)

You can run the tools directly using Python without any binary compilation:

```bash
# Run Patcher
python3 patcher/gui_patcher.py

# Run Save Editor
python3 save_editor/run_gui.py

# Run Unit Tests
python3 -m unittest discover -s save_editor/tests -v
python3 -m unittest patcher/test_patcher.py -v
```

---

## Security & Transparency

The executables distributed on Nexus Mods contain only the Python interpreter and the scripts in this repository. All code is open-source and can be inspected and reproduced deterministically.

## License & Credits

- **PS1 Translation Author**: nhojunior and localization team (v1.1a).
- **PC Port & Tooling Developer**: Mailson Maia Alves.
- **Game Copyright**: CAPCOM Co., Ltd. & GOG.com.
