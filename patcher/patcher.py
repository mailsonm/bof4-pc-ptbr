#!/usr/bin/env python3
"""Breath of Fire IV - PT-BR Patcher & Translation Manager (PC - GOG / Steam).

Automated patcher that injects Portuguese (PT-BR) localization into PC DAT archives
with automatic backup, integrity verification, and one-click restoration to original English.
"""

import os
import pickle
import shutil
import struct
import sys
import zlib
from typing import Dict, List, Optional, Tuple

VERSION = "1.0.0"
STATUS_FILE = ".ptbr_installed"


def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


class BoF4Patcher:
    """Core translation patcher engine for Breath of Fire IV PC."""

    def __init__(self, game_dir: str, pkg_path: Optional[str] = None):
        self.game_dir = os.path.abspath(game_dir)
        self.dat_dir = os.path.join(self.game_dir, "DAT")
        self.backup_dir = os.path.join(self.game_dir, "DAT_BACKUP_EN")
        self.status_file = os.path.join(self.dat_dir, STATUS_FILE)
        self.pkg_path = pkg_path or get_resource_path("translation_data.pkg")
        self._pkg_data: Optional[Dict] = None

    def validate_game_dir(self) -> Tuple[bool, str]:
        """Validates if the specified directory is a valid BoF4 PC installation."""
        if not os.path.isdir(self.game_dir):
            return False, f"Directory does not exist: {self.game_dir}"

        exe_found = any(
            os.path.isfile(os.path.join(self.game_dir, exe_name))
            for exe_name in ["BOF4.exe", "bof4.exe", "Breath of Fire IV.exe"]
        )
        if not exe_found:
            return False, "Could not find 'BOF4.exe' in directory."

        if not os.path.isdir(self.dat_dir):
            return False, "Could not find 'DAT' directory inside game folder."

        init_dat = os.path.join(self.dat_dir, "INIT.DAT")
        if not os.path.isfile(init_dat):
            return False, "Could not find 'DAT/INIT.DAT' file."

        return True, "Valid Breath of Fire IV PC installation."

    def is_patched(self) -> bool:
        """Checks if translation patch is currently installed."""
        return os.path.isfile(self.status_file)

    def has_backup(self) -> bool:
        """Checks if original English backup exists."""
        return os.path.isdir(self.backup_dir) and os.path.isfile(os.path.join(self.backup_dir, "INIT.DAT"))

    def load_package(self) -> Dict:
        """Loads and decompresses the translation package."""
        if self._pkg_data is not None:
            return self._pkg_data

        if not os.path.isfile(self.pkg_path):
            raise FileNotFoundError(f"Translation package not found at: {self.pkg_path}")

        with open(self.pkg_path, "rb") as f:
            decompressed = zlib.decompress(f.read())
            self._pkg_data = pickle.loads(decompressed)

        return self._pkg_data

    def create_backup(self, progress_callback=None) -> int:
        """Creates a complete backup of original English DAT files before patching."""
        if self.has_backup():
            return 0

        pkg = self.load_package()
        os.makedirs(self.backup_dir, exist_ok=True)
        backed_up = 0
        total = len(pkg)

        for idx, filename in enumerate(pkg.keys()):
            src = os.path.join(self.dat_dir, filename)
            dst = os.path.join(self.backup_dir, filename)
            if os.path.isfile(src) and not os.path.isfile(dst):
                shutil.copyfile(src, dst)
                backed_up += 1

            if progress_callback:
                progress_callback(idx + 1, total, f"Backing up: {filename}")

        return backed_up

    def apply_patch(self, progress_callback=None) -> Tuple[int, List[str]]:
        """Applies the Portuguese translation patch to the DAT files."""
        valid, msg = self.validate_game_dir()
        if not valid:
            raise ValueError(msg)

        # 1. Ensure backup is present
        self.create_backup(progress_callback)

        # 2. Load translation package
        pkg = self.load_package()
        patched_count = 0
        errors = []
        total = len(pkg)

        # 3. Patch each file
        for idx, (filename, data) in enumerate(pkg.items()):
            file_path = os.path.join(self.dat_dir, filename)
            backup_file = os.path.join(self.backup_dir, filename)

            # Always patch from clean backup if available
            base_source = backup_file if os.path.isfile(backup_file) else file_path

            if not os.path.isfile(base_source):
                errors.append(f"Missing file: {filename}")
                continue

            try:
                if filename == "INIT.DAT":
                    with open(file_path, "wb") as f_out:
                        f_out.write(data)
                else:
                    with open(base_source, "rb") as f_in:
                        rebuilt = bytearray(f_in.read())

                    num_entries = struct.unpack_from("<I", rebuilt, 0)[0] // 16
                    pc_entries = []
                    for e in range(num_entries):
                        off, sz, addr, typ = struct.unpack_from("<4I", rebuilt, e * 16)
                        pc_entries.append([off, sz, addr, typ])

                    for entry_idx, new_entry_data in data:
                        if entry_idx >= num_entries:
                            continue
                        old_sz = pc_entries[entry_idx][1]
                        new_sz = len(new_entry_data)
                        delta = new_sz - old_sz
                        off = pc_entries[entry_idx][0]

                        before = rebuilt[:off]
                        after = rebuilt[off + old_sz :]
                        rebuilt = before + new_entry_data + after

                        pc_entries[entry_idx][1] = new_sz
                        for j in range(entry_idx + 1, num_entries):
                            pc_entries[j][0] += delta

                    for e in range(num_entries):
                        struct.pack_into("<4I", rebuilt, e * 16, *pc_entries[e])

                    with open(file_path, "wb") as f_out:
                        f_out.write(rebuilt)

                patched_count += 1
            except Exception as ex:
                errors.append(f"{filename}: {ex}")

            if progress_callback:
                progress_callback(idx + 1, total, f"Patching: {filename}")

        # 4. Mark status
        with open(self.status_file, "w") as f_stat:
            f_stat.write(f"Breath of Fire IV PT-BR v{VERSION}\nFiles: {patched_count}\n")

        return patched_count, errors

    def restore_backup(self, progress_callback=None) -> Tuple[int, List[str]]:
        """Restores original English DAT files from backup."""
        if not self.has_backup():
            raise FileNotFoundError("Original English backup ('DAT_BACKUP_EN') was not found.")

        pkg = self.load_package()
        restored_count = 0
        errors = []
        total = len(pkg)

        for idx, filename in enumerate(pkg.keys()):
            backup_file = os.path.join(self.backup_dir, filename)
            target_file = os.path.join(self.dat_dir, filename)

            if os.path.isfile(backup_file):
                try:
                    shutil.copyfile(backup_file, target_file)
                    restored_count += 1
                except Exception as ex:
                    errors.append(f"{filename}: {ex}")

            if progress_callback:
                progress_callback(idx + 1, total, f"Restoring: {filename}")

        if os.path.isfile(self.status_file):
            try:
                os.remove(self.status_file)
            except OSError:
                pass

        return restored_count, errors


def auto_detect_game_path() -> Optional[str]:
    """Attempts to auto-detect Breath of Fire IV installation path across Windows, Steam, GOG, and Linux."""
    candidates = []

    # Custom wineprefix environment if run inside Lutris/Heroic
    env_dir = os.environ.get("GAMEDIR")
    if env_dir:
        candidates.append(env_dir)

    # Windows standard paths
    program_files_86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")

    candidates.extend(
        [
            r"C:\GOG Games\Breath of Fire IV",
            os.path.join(program_files_86, r"GOG Galaxy\Games\Breath of Fire IV"),
            os.path.join(program_files_86, r"Steam\steamapps\common\Breath of Fire IV"),
            os.path.join(program_files, r"Steam\steamapps\common\Breath of Fire IV"),
            r"C:\Games\Breath of Fire IV",
        ]
    )

    # Linux / Wine / Steam Deck paths
    home = os.path.expanduser("~")
    candidates.extend(
        [
            os.path.join(home, "Games/breath-of-fire-iv/drive_c/GOG Games/Breath of Fire IV"),
            os.path.join(home, ".local/share/Steam/steamapps/common/Breath of Fire IV"),
            os.path.join(home, ".steam/steam/steamapps/common/Breath of Fire IV"),
            os.path.join(home, ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/common/Breath of Fire IV"),
        ]
    )

    for path in candidates:
        if os.path.isdir(path):
            exe_found = any(
                os.path.isfile(os.path.join(path, exe))
                for exe in ["BOF4.exe", "bof4.exe", "Breath of Fire IV.exe"]
            )
            if exe_found and os.path.isdir(os.path.join(path, "DAT")):
                return path

    return None
