"""Surgical PE32 Patcher for Breath of Fire IV (PC GOG/2003 English) BOF4.exe.

Applies strictly verified binary patches to enable native PT-BR accented glyphs
(0x88..0xA1) and localize the few hardcoded UI strings inside BOF4.exe:
  1. VWF_dlg (0x0094CE4C) and VWF_24 (0x00952F80) extended in-place for 0x88..0xA1.
  2. VWF_16 (130 glyphs, 0x20..0xA1) relocated to verified 0-xref .text cave
     VA 0x006A7800 (Raw 0x2A7A00, with 64-byte zero base at VA 0x006A77C0),
     updating all 7 imm32 code references. (NEVER touches live .bss globals at
     .data tail 0x00967A12..0x00967FFF!)
  3. Title menu strings (16x16 slot 0, verified unsigned movzx @ 0x00628D4D):
       NEW  GAME -> NOVO JOGO
       LOAD GAME -> CARREGAR
       OPTION    -> OPÇÕES (bytes: O P 0x9F 0x9D E S)
  4. Minigame HUD strings:
       BEST       -> MELHOR (in-place)
       NEW RECORD -> NOVO RECORDE (redirected to verified 0-xref .rdata cave
                     VA 0x008D3F34 / Raw 0x2BE134)
  5. Compass directions (pointer-redirect ONLY to avoid mutating MSVC-pooled
     PC keyboard key-name strings):
       E (0x008D4BDC) -> L (0x008D4B94)
       W (0x008D4BE0) -> O (0x008D4BC4)
  6. PE hygiene: zero invalidated Authenticode SecurityDir (DataDirectory[4])
     and recalculate valid Windows OptionalHeader.CheckSum.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bof4_ptbr.font_builder import (
    CHAR_TO_BYTE,
    PTBR_CHARS,
    PTBR_START_CODE,
    PTBR_VWF_16,
    PTBR_VWF_24,
    VANILLA_GLYPH_COUNT,
)

# Clean GOG English BOF4.exe (3,634,056 bytes)
CLEAN_BOF4_EXE_SHA256: str = (
    "a529e1cc3c6c1d7236d6555191945e14f8bf417d766456d4efebaecbd6527d18"
)
CLEAN_BOF4_EXE_SIZE: int = 3_634_056

# PE header offsets (verified for e_lfanew == 0x100)
PE_LFANEW_OFFSET: int = 0x3C
EXPECTED_E_LFANEW: int = 0x100
PE_CHECKSUM_OFFSET: int = EXPECTED_E_LFANEW + 24 + 64  # 0x158
PE_SECURITY_DIR_OFFSET: int = EXPECTED_E_LFANEW + 24 + 96 + (4 * 8)  # 0x198
EXPECTED_SECURITY_DIR: bytes = struct.pack("<II", 0x00375200, 0x00002188)

# Section raw <-> VA constants
TEXT_VA_BASE: int = 0x00401000
TEXT_RAW_BASE: int = 0x00001200
RDATA_VA_BASE: int = 0x008BE000
RDATA_RAW_BASE: int = 0x002A8200
DATA_VA_BASE: int = 0x008D4000
DATA_RAW_BASE: int = 0x002BE200

# VWF table locations
VWF_DLG_PTBR_RAW: int = 0x33704C   # VA 0x0094CE4C (52 zero bytes free)
VWF_24_PTBR_RAW: int = 0x33D180    # VA 0x00952F80 (52 zero bytes free)
VWF_16_ORIG_RAW: int = 0x33CFE0    # VA 0x00952DE0 (104 * 2 = 208 bytes)
VWF_16_ORIG_VA: int = 0x00952DE0
VWF_16_ORIG_C2_VA: int = 0x00952DA1  # VWF_16_ORIG_VA - 0x40 + 1

# Verified 0-xref .text tail safe cave for relocated 16px VWF table
VWF_16_CAVE_BASE_VA: int = 0x006A77C0   # 64 zero bytes before glyph 0 (-0x40 base)
VWF_16_CAVE_BASE_RAW: int = 0x2A79C0
VWF_16_NEW_VA: int = 0x006A7800         # glyph_id 0..129 (260 bytes)
VWF_16_NEW_RAW: int = 0x2A7A00
VWF_16_NEW_C2_VA: int = 0x006A77C1      # VWF_16_NEW_VA - 0x40 + 1

# All 7 imm32 code references to VWF_16 in .text (Raw = VA - 0x3FFE00)
VWF_16_CODE_REFS: list[tuple[str, int, int, int]] = [
    ("vwf16_lb_ref_1",  0x229BE4, VWF_16_ORIG_VA,     VWF_16_NEW_VA),      # VA 0x6299E4
    ("vwf16_lb_ref_2",  0x22A82D, VWF_16_ORIG_VA,     VWF_16_NEW_VA),      # VA 0x62A62D
    ("vwf16_adv_ref_1", 0x229BEE, VWF_16_ORIG_VA + 1, VWF_16_NEW_VA + 1),  # VA 0x6299EE
    ("vwf16_adv_ref_2", 0x22A837, VWF_16_ORIG_VA + 1, VWF_16_NEW_VA + 1),  # VA 0x62A637
    ("vwf16_c2_ref_1",  0x22A137, VWF_16_ORIG_C2_VA,  VWF_16_NEW_C2_VA),   # VA 0x629F37
    ("vwf16_c2_ref_2",  0x22A54A, VWF_16_ORIG_C2_VA,  VWF_16_NEW_C2_VA),   # VA 0x62A34A
    ("vwf16_c2_ref_3",  0x22A935, VWF_16_ORIG_C2_VA,  VWF_16_NEW_C2_VA),   # VA 0x62A735
]

# Verified 0-xref .rdata tail safe cave for redirected UI strings
RDATA_CAVE_NEW_RECORD_VA: int = 0x008D3F34
RDATA_CAVE_NEW_RECORD_RAW: int = 0x2BE134
NEW_RECORD_ORIG_VA: int = 0x0090EFA4
NEW_RECORD_XREFS: list[tuple[str, int]] = [
    ("new_record_xref_1", 0x07B309),  # VA 0x0047B109
    ("new_record_xref_2", 0x07B39D),  # VA 0x0047B19D
]

# Compass pointer-redirect targets (reusing existing 'L' and 'O' in key table)
COMPASS_E_XREF_RAW: int = 0x0795E6   # VA 0x004793E6
COMPASS_W_XREF_RAW: int = 0x0795D5   # VA 0x004793D5
COMPASS_E_ORIG_VA: int = 0x008D4BDC  # 'E'
COMPASS_W_ORIG_VA: int = 0x008D4BE0  # 'W'
COMPASS_L_VA: int = 0x008D4B94       # 'L' (Raw 0x2BED94)
COMPASS_O_VA: int = 0x008D4BC4       # 'O' (Raw 0x2BEDC4)


class ExePatchError(RuntimeError):
    """Raised when BOF4.exe verification or patching fails."""


@dataclass(frozen=True)
class PatchOp:
    """Single verified byte-range replacement inside BOF4.exe."""

    name: str
    offset: int
    expected: bytes
    replacement: bytes

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "offset": self.offset,
            "expected_hex": self.expected.hex(),
            "replacement_hex": self.replacement.hex(),
        }


def encode_exe_ptbr_string(text: str, slot_size: int) -> bytes:
    """Encode a PT-BR string using BOF4 PC font bytes (0x20..0xA1), null-padded."""
    raw = bytearray()
    for ch in text:
        if ch in CHAR_TO_BYTE:
            raw.append(CHAR_TO_BYTE[ch])
        else:
            code = ord(ch)
            if not (0x20 <= code <= 0x7D):
                raise ExePatchError(f"Unsupported EXE UI character: {ch!r}")
            raw.append(code)
    if len(raw) + 1 > slot_size:
        raise ExePatchError(
            f"Encoded string {text!r} ({len(raw) + 1} B with null) "
            f"exceeds slot size {slot_size} B"
        )
    return bytes(raw) + b"\x00" * (slot_size - len(raw))


def _pack_vwf_entries(vwf_map: dict[int, tuple[int, int]]) -> bytes:
    out = bytearray()
    for idx in range(len(PTBR_CHARS)):
        code = PTBR_START_CODE + idx
        if code not in vwf_map:
            raise ExePatchError(f"Missing VWF metric for byte 0x{code:02X}")
        lb, adv = vwf_map[code]
        if not (0 <= lb <= 64 and 0 <= adv <= 64):
            raise ExePatchError(f"Out-of-range VWF metric for 0x{code:02X}: {(lb, adv)}")
        out.append(lb)
        out.append(adv)
    return bytes(out)


def calculate_pe_checksum(pe_bytes: bytes) -> int:
    """Compute standard Windows ImageHlp MapFileAndCheckSum PE32 checksum."""
    if len(pe_bytes) < 0x40:
        raise ExePatchError("PE buffer too small")
    e_lfanew = struct.unpack_from("<I", pe_bytes, PE_LFANEW_OFFSET)[0]
    checksum_offset = e_lfanew + 24 + 64
    if checksum_offset + 4 > len(pe_bytes):
        raise ExePatchError("Invalid PE header checksum offset")

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


def verify_pe_checksum(pe_bytes: bytes) -> bool:
    """Return True iff PE OptionalHeader.CheckSum matches calculated checksum."""
    e_lfanew = struct.unpack_from("<I", pe_bytes, PE_LFANEW_OFFSET)[0]
    stored = struct.unpack_from("<I", pe_bytes, e_lfanew + 24 + 64)[0]
    return stored == calculate_pe_checksum(pe_bytes)


def build_patch_ops(
    clean_exe_bytes: bytes,
    vwf_24: dict[int, tuple[int, int]] | None = None,
    vwf_16: dict[int, tuple[int, int]] | None = None,
) -> list[PatchOp]:
    """Construct the full ordered list of verified PatchOps for clean BOF4.exe."""
    m24 = PTBR_VWF_24 if vwf_24 is None else vwf_24
    m16 = PTBR_VWF_16 if vwf_16 is None else vwf_16

    vwf24_blob = _pack_vwf_entries(m24)
    vwf16_ptbr_blob = _pack_vwf_entries(m16)
    vwf16_vanilla = clean_exe_bytes[
        VWF_16_ORIG_RAW : VWF_16_ORIG_RAW + VANILLA_GLYPH_COUNT * 2
    ]
    if len(vwf16_vanilla) != VANILLA_GLYPH_COUNT * 2:
        raise ExePatchError("Failed to read vanilla 16px VWF table from BOF4.exe")

    # 64 zero bytes (-0x40 base) + 208 vanilla bytes + 52 PT-BR bytes = 324 bytes
    vwf16_cave_payload = (b"\x00" * 64) + vwf16_vanilla + vwf16_ptbr_blob

    ops: list[PatchOp] = [
        # 1. Extend VWF_dlg & VWF_24 in-place
        PatchOp("vwf_dlg_ptbr", VWF_DLG_PTBR_RAW, b"\x00" * 52, vwf24_blob),
        PatchOp("vwf_24_ptbr", VWF_24_PTBR_RAW, b"\x00" * 52, vwf24_blob),
        # 2. Relocate full 130-glyph VWF_16 to .text safe cave VA 0x006A7800
        PatchOp(
            "vwf_16_cave_table",
            VWF_16_CAVE_BASE_RAW,
            b"\x00" * len(vwf16_cave_payload),
            vwf16_cave_payload,
        ),
    ]

    for name, raw_off, old_va, new_va in VWF_16_CODE_REFS:
        ops.append(
            PatchOp(
                name,
                raw_off,
                struct.pack("<I", old_va),
                struct.pack("<I", new_va),
            )
        )

    # 3. Title Menu UI strings (16x16 slot 0, verified unsigned movzx @ 0x628D4D)
    ops.extend(
        [
            PatchOp(
                "title_new_game",
                0x3407AC,
                b"NEW  GAME\x00\x00\x00",
                encode_exe_ptbr_string("NOVO JOGO", 12),
            ),
            PatchOp(
                "title_load_game",
                0x3407A0,
                b"LOAD GAME\x00\x00\x00",
                encode_exe_ptbr_string("CARREGAR", 12),
            ),
            PatchOp(
                "title_option",
                0x340798,
                b"OPTION\x00\x00",
                encode_exe_ptbr_string("OPÇÕES", 8),
            ),
        ]
    )

    # 4. Minigame HUD strings (BEST in-place; NEW RECORD redirected to .rdata cave)
    new_record_ptbr = encode_exe_ptbr_string("NOVO RECORDE", 16)
    ops.extend(
        [
            PatchOp(
                "hud_best",
                0x2F918C,
                b"BEST\x00\x00\x00\x00",
                encode_exe_ptbr_string("MELHOR", 8),
            ),
            PatchOp(
                "hud_new_record_cave",
                RDATA_CAVE_NEW_RECORD_RAW,
                b"\x00" * len(new_record_ptbr),
                new_record_ptbr,
            ),
        ]
    )
    for name, raw_off in NEW_RECORD_XREFS:
        ops.append(
            PatchOp(
                name,
                raw_off,
                struct.pack("<I", NEW_RECORD_ORIG_VA),
                struct.pack("<I", RDATA_CAVE_NEW_RECORD_VA),
            )
        )

    # 5. Compass E/W -> L/O (pointer-redirect only; preserves pooled PC key table)
    # Also assert target 'L' and 'O' exist at their expected offsets.
    ops.extend(
        [
            PatchOp("verify_key_L", 0x2BED94, b"L\x00", b"L\x00"),
            PatchOp("verify_key_O", 0x2BEDC4, b"O\x00", b"O\x00"),
            PatchOp(
                "compass_E_to_L",
                COMPASS_E_XREF_RAW,
                struct.pack("<I", COMPASS_E_ORIG_VA),
                struct.pack("<I", COMPASS_L_VA),
            ),
            PatchOp(
                "compass_W_to_O",
                COMPASS_W_XREF_RAW,
                struct.pack("<I", COMPASS_W_ORIG_VA),
                struct.pack("<I", COMPASS_O_VA),
            ),
        ]
    )

    # 6. Zero invalidated Authenticode SecurityDir (DataDirectory[4])
    ops.append(
        PatchOp(
            "pe_zero_security_dir",
            PE_SECURITY_DIR_OFFSET,
            EXPECTED_SECURITY_DIR,
            b"\x00" * 8,
        )
    )

    return ops


def patch_exe_bytes(
    exe_bytes: bytes,
    vwf_24: dict[int, tuple[int, int]] | None = None,
    vwf_16: dict[int, tuple[int, int]] | None = None,
    verify_sha256: bool = True,
) -> bytes:
    """Validate clean BOF4.exe bytes and return patched PE32 bytes with valid CheckSum."""
    if len(exe_bytes) != CLEAN_BOF4_EXE_SIZE:
        raise ExePatchError(
            f"Unexpected BOF4.exe size: {len(exe_bytes)} (expected {CLEAN_BOF4_EXE_SIZE})"
        )
    if verify_sha256:
        actual_sha = hashlib.sha256(exe_bytes).hexdigest()
        if actual_sha != CLEAN_BOF4_EXE_SHA256:
            raise ExePatchError(
                f"BOF4.exe SHA256 mismatch: got {actual_sha}, "
                f"expected clean GOG English {CLEAN_BOF4_EXE_SHA256}"
            )

    e_lfanew = struct.unpack_from("<I", exe_bytes, PE_LFANEW_OFFSET)[0]
    if e_lfanew != EXPECTED_E_LFANEW:
        raise ExePatchError(
            f"Unexpected PE e_lfanew: 0x{e_lfanew:X} (expected 0x{EXPECTED_E_LFANEW:X})"
        )

    ops = build_patch_ops(exe_bytes, vwf_24=vwf_24, vwf_16=vwf_16)

    # Strict pre-flight verification of EVERY target byte range before mutating anything
    for op in ops:
        if len(op.expected) != len(op.replacement):
            raise ExePatchError(
                f"PatchOp {op.name} length mismatch: "
                f"{len(op.expected)} vs {len(op.replacement)}"
            )
        actual = exe_bytes[op.offset : op.offset + len(op.expected)]
        if actual != op.expected:
            raise ExePatchError(
                f"Pre-flight byte mismatch at {op.name} (Raw 0x{op.offset:06X}): "
                f"got {actual[:16].hex()}, expected {op.expected[:16].hex()}"
            )

    buf = bytearray(exe_bytes)
    for op in ops:
        buf[op.offset : op.offset + len(op.replacement)] = op.replacement

    # Recalculate and write valid PE OptionalHeader.CheckSum
    new_cs = calculate_pe_checksum(bytes(buf))
    struct.pack_into("<I", buf, PE_CHECKSUM_OFFSET, new_cs)
    return bytes(buf)


def build_exe_patch_spec(
    clean_exe_bytes: bytes,
    vwf_24: dict[int, tuple[int, int]] | None = None,
    vwf_16: dict[int, tuple[int, int]] | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable deterministic BOF4.exe patch spec for packaging."""
    ops = build_patch_ops(clean_exe_bytes, vwf_24=vwf_24, vwf_16=vwf_16)
    patched = patch_exe_bytes(clean_exe_bytes, vwf_24=vwf_24, vwf_16=vwf_16)
    orig_cs = clean_exe_bytes[PE_CHECKSUM_OFFSET : PE_CHECKSUM_OFFSET + 4]
    new_cs = patched[PE_CHECKSUM_OFFSET : PE_CHECKSUM_OFFSET + 4]

    full_ops = [op for op in ops if op.expected != op.replacement]
    full_ops.append(PatchOp("pe_checksum", PE_CHECKSUM_OFFSET, orig_cs, new_cs))

    return {
        "target_file": "BOF4.exe",
        "clean_sha256": CLEAN_BOF4_EXE_SHA256,
        "patched_sha256": hashlib.sha256(patched).hexdigest(),
        "pe_checksum": struct.unpack("<I", new_cs)[0],
        "ops": [op.to_dict() for op in full_ops],
    }


def apply_exe_patch(
    exe_path: str | Path,
    create_backup: bool = True,
    vwf_24: dict[int, tuple[int, int]] | None = None,
    vwf_16: dict[int, tuple[int, int]] | None = None,
) -> dict[str, Any]:
    """Patch BOF4.exe on disk atomically after verifying clean SHA256 and target bytes.

    If ``create_backup`` is True, saves the original clean executable to
    ``<exe_path>.bak`` (e.g. ``BOF4.exe.bak``) without overwriting an existing backup.
    """
    target = Path(exe_path)
    if not target.is_file():
        raise ExePatchError(f"Executable not found: {target}")

    original = target.read_bytes()
    patched = patch_exe_bytes(original, vwf_24=vwf_24, vwf_16=vwf_16, verify_sha256=True)

    backup_path = Path(str(target) + ".bak")
    if create_backup and not backup_path.exists():
        shutil.copy2(target, backup_path)

    tmp_path = target.with_name(target.name + ".tmp_ptbr")
    try:
        tmp_path.write_bytes(patched)
        os.replace(tmp_path, target)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    return {
        "exe_path": str(target),
        "backup_path": str(backup_path) if create_backup else None,
        "clean_sha256": CLEAN_BOF4_EXE_SHA256,
        "patched_sha256": hashlib.sha256(patched).hexdigest(),
        "pe_checksum": calculate_pe_checksum(patched),
        "pe_checksum_valid": verify_pe_checksum(patched),
    }


def restore_exe_backup(exe_path: str | Path) -> dict[str, Any]:
    """Restore BOF4.exe from BOF4.exe.bak and verify exact clean SHA256."""
    target = Path(exe_path)
    backup_path = Path(str(target) + ".bak")
    if not backup_path.is_file():
        raise ExePatchError(f"Backup file not found: {backup_path}")

    bak_bytes = backup_path.read_bytes()
    bak_sha = hashlib.sha256(bak_bytes).hexdigest()
    if bak_sha != CLEAN_BOF4_EXE_SHA256:
        raise ExePatchError(
            f"Backup SHA256 mismatch: {bak_sha} != {CLEAN_BOF4_EXE_SHA256}"
        )

    tmp_path = target.with_name(target.name + ".tmp_restore")
    try:
        tmp_path.write_bytes(bak_bytes)
        os.replace(tmp_path, target)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    restored_sha = hashlib.sha256(target.read_bytes()).hexdigest()
    return {
        "exe_path": str(target),
        "backup_path": str(backup_path),
        "restored_sha256": restored_sha,
        "clean_match": restored_sha == CLEAN_BOF4_EXE_SHA256,
    }
