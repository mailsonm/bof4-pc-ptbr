#!/usr/bin/env python3
"""Breath of Fire IV - PT-BR Patcher & Translation Manager (PC - GOG / Steam).

Self-contained v2.0.0 installer/restorer for PyInstaller and CLI usage.
Applies the native PT-BR translation package (`translation_v2.pkg`, BOF4PTV2 format):
- Patches 305 PC .DAT files (317 text entries + INIT.DAT[8..9] 16x16 & 24x24 PT-BR fonts)
  matched strictly by (type_param, dest) with 1-byte packing and .psxseg RAM ceiling checks.
- Leaves INIT.DAT[7] (item/weapon/armor/accessory/spell/key-item names) in original English.
- Patches BOF4.exe (VWF tables, Title Menu, Minigame HUD, Compass) with PE CheckSum update.
- Creates non-destructive backups in DAT_BACKUP_EN/ and BOF4.exe.bak for 1-click restoration.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import sys
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

VERSION = "2.0.0"
STATUS_FILE = ".ptbr_installed"
PKG_MAGIC = b"BOF4PTV2"
PKG_FILENAME = "translation_v2.pkg"

# Hard .psxseg RAM buffer ceilings for Type 0 text entries
_TEXT_DEST_CEILINGS: Dict[int, int] = {
    0x00000: 0x10000,
    0x10000: 0x10000,
    0x20000: 0x07000,
    0x27000: 0x01000,
}
_CATALOG_DEST = 0x28000


def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def _atomic_write(path: str, data: bytes) -> None:
    tmp_path = f"{path}.tmp_ptbr"
    try:
        with open(tmp_path, "wb") as f:
            f.write(data)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


def _calculate_pe_checksum(pe_bytes: bytes) -> int:
    """Compute standard Windows PE32 OptionalHeader.CheckSum."""
    if len(pe_bytes) < 0x40:
        raise ValueError("PE buffer too small")
    e_lfanew = struct.unpack_from("<I", pe_bytes, 0x3C)[0]
    checksum_offset = e_lfanew + 24 + 64
    if checksum_offset + 4 > len(pe_bytes):
        raise ValueError("Invalid PE header checksum offset")

    total = 0
    length = len(pe_bytes)
    even_len = length - (length & 1)
    for i in range(0, even_len, 2):
        if i == checksum_offset or i == checksum_offset + 2:
            continue
        word = pe_bytes[i] | (pe_bytes[i + 1] << 8)
        total += word
        total = (total & 0xFFFF) + (total >> 16)
    if length & 1:
        total += pe_bytes[-1]
        total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (total + length) & 0xFFFFFFFF


def _verify_pe_checksum(pe_bytes: bytes) -> bool:
    e_lfanew = struct.unpack_from("<I", pe_bytes, 0x3C)[0]
    stored = struct.unpack_from("<I", pe_bytes, e_lfanew + 24 + 64)[0]
    return stored == _calculate_pe_checksum(pe_bytes)


def _patch_dat_bytes(raw: bytes, ops: List[Dict], blob_stream: bytes, filename: str) -> bytes:
    """Replaces entries matched strictly by (type_param, dest) and re-packs with 0 gaps."""
    fsize = len(raw)
    if fsize < 16:
        raise ValueError(f"Invalid DAT file {filename}: size {fsize} < 16")
    first_off = struct.unpack_from("<I", raw, 0)[0]
    if first_off == 0 or (first_off % 16) != 0 or first_off > fsize:
        raise ValueError(f"Invalid DAT TOC header in {filename}: first_off={first_off:#x}")

    num_entries = first_off // 16
    entries: List[Tuple[int, int, bytearray]] = []
    for i in range(num_entries):
        off, sz, type_param, dest = struct.unpack_from("<4I", raw, i * 16)
        if off > fsize or off + sz > fsize:
            raise ValueError(f"Entry {i} out of bounds in {filename}")
        entries.append((type_param, dest, bytearray(raw[off : off + sz])))

    for op in ops:
        target_tp = int(op["type_param"])
        target_dest = int(op["dest"])
        if target_tp == 0 and target_dest == _CATALOG_DEST:
            raise PermissionError("Refusing to patch INIT.DAT[7] catalog")

        b_off = int(op["blob_off"])
        b_len = int(op["blob_len"])
        payload = blob_stream[b_off : b_off + b_len]
        if len(payload) != b_len or hashlib.sha256(payload).hexdigest() != op["sha256"]:
            raise ValueError(f"Corrupted blob payload for {filename} dest={target_dest:#x}")

        if target_tp == 0 and target_dest in _TEXT_DEST_CEILINGS:
            ceiling = _TEXT_DEST_CEILINGS[target_dest]
            if len(payload) > ceiling:
                raise ValueError(
                    f"Payload for {filename} dest={target_dest:#x} ({len(payload)} B) "
                    f"exceeds .psxseg ceiling ({ceiling} B)"
                )

        matches = [
            idx
            for idx, (tp, dest, _data) in enumerate(entries)
            if tp == target_tp and dest == target_dest
        ]
        if len(matches) != 1:
            raise KeyError(
                f"Expected unique (type_param={target_tp:#x}, dest={target_dest:#x}) "
                f"in {filename}, found {len(matches)}"
            )
        entries[matches[0]] = (target_tp, target_dest, bytearray(payload))

    toc_size = num_entries * 16
    out = bytearray(toc_size)
    cur_off = toc_size
    for i, (tp, dest, payload_buf) in enumerate(entries):
        sz = len(payload_buf)
        struct.pack_into("<4I", out, i * 16, cur_off, sz, tp, dest)
        cur_off += sz
    for _tp, _dest, payload_buf in entries:
        out.extend(payload_buf)
    return bytes(out)


def _patch_exe_bytes(exe_bytes: bytes, spec: Dict) -> bytes:
    """Applies verified PatchOps to clean BOF4.exe and verifies SHA256 + PE CheckSum."""
    clean_sha = spec["clean_sha256"]
    actual_sha = hashlib.sha256(exe_bytes).hexdigest()
    if actual_sha != clean_sha:
        raise ValueError(
            f"BOF4.exe SHA256 mismatch: got {actual_sha}, expected clean {clean_sha}"
        )

    buf = bytearray(exe_bytes)
    for op in spec["ops"]:
        off = int(op["offset"])
        expected = bytes.fromhex(op["expected_hex"])
        replacement = bytes.fromhex(op["replacement_hex"])
        actual = bytes(buf[off : off + len(expected)])
        if actual != expected:
            raise ValueError(
                f"BOF4.exe pre-flight mismatch at {op['name']} (0x{off:06X})"
            )
        buf[off : off + len(replacement)] = replacement

    patched = bytes(buf)
    if hashlib.sha256(patched).hexdigest() != spec["patched_sha256"]:
        raise ValueError("Patched BOF4.exe SHA256 verification failed")
    if not _verify_pe_checksum(patched):
        raise ValueError("Patched BOF4.exe PE CheckSum verification failed")
    return patched


class BoF4Patcher:
    """Core v2.0.0 translation patcher engine for Breath of Fire IV PC."""

    def __init__(self, game_dir: str, pkg_path: Optional[str] = None):
        self.game_dir = os.path.abspath(game_dir)
        self.dat_dir = os.path.join(self.game_dir, "DAT")
        self.backup_dir = os.path.join(self.game_dir, "DAT_BACKUP_EN")
        self.exe_path = self._find_exe_path()
        self.exe_backup_path = f"{self.exe_path}.bak"
        self.status_file = os.path.join(self.dat_dir, STATUS_FILE)
        self.pkg_path = pkg_path or get_resource_path(PKG_FILENAME)
        self._pkg_meta: Optional[Dict] = None
        self._blob_stream: Optional[bytes] = None

    def _find_exe_path(self) -> str:
        for exe_name in ("BOF4.exe", "bof4.exe", "Breath of Fire IV.exe"):
            candidate = os.path.join(self.game_dir, exe_name)
            if os.path.isfile(candidate):
                return candidate
        return os.path.join(self.game_dir, "BOF4.exe")

    def validate_game_dir(self) -> Tuple[bool, str]:
        """Validates if the specified directory is a valid BoF4 PC installation."""
        if not os.path.isdir(self.game_dir):
            return False, f"Directory does not exist: {self.game_dir}"

        self.exe_path = self._find_exe_path()
        self.exe_backup_path = f"{self.exe_path}.bak"
        if not os.path.isfile(self.exe_path):
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
        return os.path.isdir(self.backup_dir) and os.path.isfile(
            os.path.join(self.backup_dir, "INIT.DAT")
        )

    def load_package(self) -> Dict:
        """Loads, decompresses, and SHA256-verifies the BOF4PTV2 translation package."""
        if self._pkg_meta is not None:
            return self._pkg_meta

        if not os.path.isfile(self.pkg_path):
            raise FileNotFoundError(f"Translation package not found at: {self.pkg_path}")

        with open(self.pkg_path, "rb") as f:
            raw = f.read()

        if len(raw) < len(PKG_MAGIC) + 4 or raw[: len(PKG_MAGIC)] != PKG_MAGIC:
            raise ValueError(f"Invalid translation package header in: {self.pkg_path}")

        body = zlib.decompress(raw[len(PKG_MAGIC) :])
        meta_len = struct.unpack_from("<I", body, 0)[0]
        meta_bytes = body[4 : 4 + meta_len]
        blob_stream = body[4 + meta_len :]
        meta = json.loads(meta_bytes.decode("utf-8"))

        if meta.get("format") != "bof4_ptbr_v2":
            raise ValueError(f"Unsupported package format: {meta.get('format')!r}")

        # Verify SHA256 of every blob referenced in dat_patches
        verified: set[Tuple[int, int, str]] = set()
        for fname, ops in meta["dat_patches"].items():
            for op in ops:
                key = (op["blob_off"], op["blob_len"], op["sha256"])
                if key in verified:
                    continue
                blob = blob_stream[op["blob_off"] : op["blob_off"] + op["blob_len"]]
                if len(blob) != op["blob_len"] or hashlib.sha256(blob).hexdigest() != op["sha256"]:
                    raise ValueError(f"Corrupted package blob for {fname}")
                verified.add(key)

        self._pkg_meta = meta
        self._blob_stream = blob_stream
        return self._pkg_meta

    def create_backup(self, progress_callback=None) -> int:
        """Creates backups of all target English DAT files and BOF4.exe before patching."""
        meta = self.load_package()
        dat_patches: Dict[str, List[Dict]] = meta["dat_patches"]
        os.makedirs(self.backup_dir, exist_ok=True)
        backed_up = 0
        total = len(dat_patches) + 1

        for idx, filename in enumerate(sorted(dat_patches.keys())):
            src = os.path.join(self.dat_dir, filename)
            dst = os.path.join(self.backup_dir, filename)
            if os.path.isfile(src) and not os.path.isfile(dst):
                shutil.copy2(src, dst)
                backed_up += 1
            if progress_callback:
                progress_callback(idx + 1, total, f"Backup: {filename}")

        if os.path.isfile(self.exe_path) and not os.path.isfile(self.exe_backup_path):
            shutil.copy2(self.exe_path, self.exe_backup_path)
            backed_up += 1
        if progress_callback:
            progress_callback(total, total, f"Backup: {os.path.basename(self.exe_path)}")

        return backed_up

    def apply_patch(self, progress_callback=None) -> Tuple[int, List[str]]:
        """Applies the v2.0.0 native PT-BR patch to DAT files and BOF4.exe."""
        valid, msg = self.validate_game_dir()
        if not valid:
            raise ValueError(msg)

        self.create_backup(progress_callback)

        meta = self.load_package()
        assert self._blob_stream is not None
        blob_stream = self._blob_stream
        dat_patches: Dict[str, List[Dict]] = meta["dat_patches"]
        exe_spec: Dict = meta["exe_patch_spec"]

        patched_count = 0
        errors: List[str] = []
        total = len(dat_patches) + 1

        # 1. Patch BOF4.exe from clean backup
        exe_src = self.exe_backup_path if os.path.isfile(self.exe_backup_path) else self.exe_path
        with open(exe_src, "rb") as f_exe:
            clean_exe_bytes = f_exe.read()
        patched_exe = _patch_exe_bytes(clean_exe_bytes, exe_spec)
        _atomic_write(self.exe_path, patched_exe)
        patched_count += 1
        if progress_callback:
            progress_callback(1, total, f"Patching: {os.path.basename(self.exe_path)}")

        # 2. Patch every target DAT strictly by (type_param, dest) from clean backup
        for idx, filename in enumerate(sorted(dat_patches.keys())):
            ops = dat_patches[filename]
            file_path = os.path.join(self.dat_dir, filename)
            backup_file = os.path.join(self.backup_dir, filename)
            base_source = backup_file if os.path.isfile(backup_file) else file_path

            if not os.path.isfile(base_source):
                errors.append(f"Missing file: {filename}")
                continue

            try:
                with open(base_source, "rb") as f_in:
                    raw_dat = f_in.read()
                rebuilt = _patch_dat_bytes(raw_dat, ops, blob_stream, filename)
                _atomic_write(file_path, rebuilt)
                patched_count += 1
            except Exception as ex:
                errors.append(f"{filename}: {ex}")

            if progress_callback:
                progress_callback(idx + 2, total, f"Patching: {filename}")

        if not errors:
            status_payload = json.dumps(
                {
                    "version": VERSION,
                    "patched_files": patched_count,
                    "exe_patched_sha256": exe_spec["patched_sha256"],
                },
                indent=2,
            )
            _atomic_write(self.status_file, status_payload.encode("utf-8"))

        return patched_count, errors

    def restore_backup(self, progress_callback=None) -> Tuple[int, List[str]]:
        """Restores original English DAT files and BOF4.exe from backup."""
        if not self.has_backup():
            raise FileNotFoundError("Original English backup ('DAT_BACKUP_EN') was not found.")

        self.exe_path = self._find_exe_path()
        self.exe_backup_path = f"{self.exe_path}.bak"

        expected_dat_files = sorted(
            f for f in os.listdir(self.backup_dir) if f.upper().endswith(".DAT")
        )
        if os.path.isfile(self.status_file):
            try:
                with open(self.status_file, "r", encoding="utf-8") as f_st:
                    st_data = json.load(f_st)
                if isinstance(st_data, dict) and "patched_dat_files" in st_data:
                    expected_dat_files = sorted(
                        set(expected_dat_files) | set(st_data["patched_dat_files"])
                    )
            except Exception:
                pass

        restored_count = 0
        errors: List[str] = []
        has_exe_bak = os.path.isfile(self.exe_backup_path)
        total = len(expected_dat_files) + (1 if has_exe_bak else 0)

        for idx, filename in enumerate(expected_dat_files):
            backup_file = os.path.join(self.backup_dir, filename)
            target_file = os.path.join(self.dat_dir, filename)
            if os.path.isfile(backup_file):
                try:
                    with open(backup_file, "rb") as f_bak:
                        _atomic_write(target_file, f_bak.read())
                    restored_count += 1
                except Exception as ex:
                    errors.append(f"{filename}: {ex}")
            else:
                errors.append(f"Missing backup: {filename}")

            if progress_callback:
                progress_callback(idx + 1, total, f"Restoring: {filename}")

        if has_exe_bak:
            try:
                with open(self.exe_backup_path, "rb") as f_exe_bak:
                    _atomic_write(self.exe_path, f_exe_bak.read())
                restored_count += 1
            except Exception as ex:
                errors.append(f"{os.path.basename(self.exe_path)}: {ex}")
            if progress_callback:
                progress_callback(total, total, f"Restoring: {os.path.basename(self.exe_path)}")

        if os.path.isfile(self.status_file):
            try:
                os.remove(self.status_file)
            except OSError:
                pass

        return restored_count, errors


def auto_detect_game_path() -> Optional[str]:
    """Attempts to auto-detect Breath of Fire IV installation path across Windows, Steam, GOG, and Linux."""
    candidates = []

    env_dir = os.environ.get("GAMEDIR")
    if env_dir:
        candidates.append(env_dir)

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

    home = os.path.expanduser("~")
    candidates.extend(
        [
            os.path.join(home, "Games/breath-of-fire-iv/drive_c/GOG Games/Breath of Fire IV"),
            os.path.join(home, ".local/share/Steam/steamapps/common/Breath of Fire IV"),
            os.path.join(home, ".steam/steam/steamapps/common/Breath of Fire IV"),
            os.path.join(
                home,
                ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/common/Breath of Fire IV",
            ),
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
