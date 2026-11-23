"""Binary parser, validator, and packed writer for Breath of Fire IV PC .DAT archives.

Container specification (verified from BOF4.exe @ 0x004E9CE0 across all 972 clean .DAT files):
- No header magic, no explicit entry count, no sentinel entry.
- TOC consists of N = (entry[0].off >> 4) contiguous 16-byte little-endian records (<4I):
    +0x00 uint32 off         Byte offset from file start (entry[0].off == N * 16)
    +0x04 uint32 sz          Exact payload length in bytes
    +0x08 uint32 type_param  Low byte = entry_type (0..5); upper 24 bits = param
    +0x0C uint32 dest        Type-specific destination/descriptor
- Payloads are 1-byte packed in strict TOC order with 0 inter-entry gaps and 0 trailing padding.
- Entry order MUST be preserved (BOF4.exe supports early-exit loading of first 2 or 4 entries).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

# TOC entry types (type_param & 0xFF) from BOF4.exe jump table @ 0x004E9FDC
TYPE_RAM = 0        # Raw memcpy to .psxseg (0x006B0000 + dest)
TYPE_VRAM_LZSS = 1  # LZSS decompress (param bytes) -> VRAM rect packed in dest
TYPE_PTR_TABLE = 2  # Raw memcpy to g_PtrTable[dest] (0xBAB5B0)
TYPE_SFX = 3        # Soundbank/SFX loader (0x66D9A0)
TYPE_BGM = 4        # BGM stream loader (0x66DA20)
TYPE_PC_FONT = 5    # PC 4bpp font loader (0x40DCE0: slot=dest&0xFF, dim=(dest>>8)&0xFF)

# Known INIT.DAT font entry descriptors (type_param == TYPE_PC_FONT)
FONT_16_DEST = 0x00001000  # Entry 8:  slot 0, 16x16 4bpp (128 B/glyph)
FONT_24_DEST = 0x00001801  # Entry 9:  slot 1, 24x24 4bpp (288 B/glyph)
FONT_12_DEST = 0x00000C02  # Entry 10: slot 2, 12x12 4bpp (72 B/glyph)
FONT_64_DEST = 0x00004003  # Entry 11: slot 3, 64x64 4bpp (2048 B/glyph)

# Portrait descriptors (never touch during text patching)
PORTRAIT_VRAM_DEST = 0x1E080200  # type=1
PORTRAIT_CLUT_DEST = 0x0002FC00  # type=0

# Authoritative .psxseg text slots (type_param == 0) and hard byte ceilings
# Verified against BOF4.exe GetTextPointer (0x5279A0) & GetGlobalCatalogName (0x66FA70)
TEXT_DEST_CEILINGS: Dict[int, int] = {
    0x00000: 0x10000,  # 65,536 B (VA 0x6B0000: map/event/battle dialogue, AB000_00[1])
    0x10000: 0x10000,  # 65,536 B (VA 0x6C0000: system prompts, BTLEND[5], item/skill descs)
    0x20000: 0x07000,  # 28,672 B (VA 0x6D0000: camp/master/shop/save/start/sgamen menus)
    0x27000: 0x01000,  #  4,096 B (VA 0x6D7000: INIT.DAT[6] PC menus/controls/regions/maps)
    0x28000: 0x06000,  # 24,576 B (VA 0x6D8000: INIT.DAT[7] 6-sec catalog before 0x2E000 CLUT)
}

CATALOG_DEST = 0x28000

# Unused Japanese leftover blobs to skip during corpus extraction
JP_STUB_MD5 = "fd162087fc17924457e79400b1ebbb3d"  # 80 identical 520-byte stub files
JP_DEBUG_FILES = frozenset({"AREAD068.DAT", "AREAS052.DAT", "AREAM019.DAT"})

# Multi-section text entries: (filename, dest) -> section_count
MULTI_SECTION_SPECS: Dict[Tuple[str, int], int] = {
    ("AB000_00.DAT", 0x00000): 2,
    ("INIT.DAT", 0x28000): 6,
}


@dataclass
class DatEntry:
    """Single TOC entry + raw payload inside a PC .DAT archive."""

    index: int
    offset: int
    size: int
    type_param: int
    dest: int
    data: bytes

    @property
    def entry_type(self) -> int:
        return self.type_param & 0xFF

    @property
    def param(self) -> int:
        return self.type_param >> 8

    @property
    def is_text(self) -> bool:
        return self.type_param == TYPE_RAM and self.dest in TEXT_DEST_CEILINGS

    @property
    def is_font(self) -> bool:
        return self.type_param == TYPE_PC_FONT


def split_multisection(raw: bytes, num_sections: int) -> List[bytes]:
    """Splits a multi-section text block (uint32[num_sections] offset header) into sub-blocks."""
    hdr_sz = num_sections * 4
    if len(raw) < hdr_sz:
        raise ValueError(f"Multi-section block too small ({len(raw)} < {hdr_sz})")
    offs = struct.unpack_from(f"<{num_sections}I", raw, 0)
    if offs[0] != hdr_sz:
        raise ValueError(f"Expected first section offset {hdr_sz:#x}, got {offs[0]:#x}")
    for i in range(num_sections):
        if offs[i] % 4 != 0:
            raise ValueError(f"Section {i} offset {offs[i]:#x} is not 4-byte aligned")
        if offs[i] >= len(raw):
            raise ValueError(f"Section {i} offset {offs[i]:#x} exceeds length {len(raw):#x}")
        if i > 0 and offs[i] <= offs[i - 1]:
            raise ValueError(f"Non-monotonic section offsets: {offs}")

    sections: List[bytes] = []
    for i in range(num_sections):
        start = offs[i]
        end = offs[i + 1] if i + 1 < num_sections else len(raw)
        sections.append(raw[start:end])
    return sections


def build_ab000_multisection(sec0_bytes: bytes, sec1_bytes: bytes) -> bytes:
    """Builds 2-section AB000_00.DAT[1] (dest=0x0) with 4-byte aligned section offsets.

    Pads sec0_bytes with 0x00 to a 4-byte boundary so section 1 starts on a 4-byte offset,
    reproducing the exact vanilla binary layout (where sec0 unpadded == BTLEND.DAT[5]).
    """
    if not sec0_bytes or not sec1_bytes:
        raise ValueError("AB000_00 multi-section sub-blocks must be non-empty")
    pad_len = (-len(sec0_bytes)) % 4
    s0_off = 8
    s1_off = s0_off + len(sec0_bytes) + pad_len
    payload = struct.pack("<2I", s0_off, s1_off) + sec0_bytes + (b"\x00" * pad_len) + sec1_bytes
    if len(payload) > TEXT_DEST_CEILINGS[0x00000]:
        raise ValueError(
            f"AB000_00.DAT[1] rebuilt size {len(payload)} exceeds 64 KiB ceiling "
            f"({TEXT_DEST_CEILINGS[0x00000]})"
        )
    return payload


class DatArchive:
    """In-memory representation of a Breath of Fire IV PC .DAT archive."""

    def __init__(self, entries: List[DatEntry], filename: Optional[str] = None) -> None:
        if not entries:
            raise ValueError("DatArchive must contain at least one entry")
        self.entries: List[DatEntry] = entries
        self.filename: Optional[str] = filename

    @classmethod
    def from_bytes(cls, raw: bytes, filename: Optional[str] = None) -> "DatArchive":
        """Parses a PC .DAT archive strictly according to BOF4.exe's TOC format."""
        fsize = len(raw)
        if fsize < 16:
            raise ValueError(f"DAT buffer too small ({fsize} bytes)")
        first_off = struct.unpack_from("<I", raw, 0)[0]
        if first_off == 0 or (first_off % 16) != 0 or first_off > fsize:
            raise ValueError(
                f"Invalid DAT TOC first_off={first_off:#x} (fsize={fsize:#x}, file={filename})"
            )

        num_entries = first_off // 16
        entries: List[DatEntry] = []
        for i in range(num_entries):
            off, sz, type_param, dest = struct.unpack_from("<4I", raw, i * 16)
            if off > fsize or off + sz > fsize:
                raise ValueError(
                    f"Entry {i} out of bounds in {filename}: off={off:#x} sz={sz:#x} fsize={fsize:#x}"
                )
            entries.append(
                DatEntry(
                    index=i,
                    offset=off,
                    size=sz,
                    type_param=type_param,
                    dest=dest,
                    data=raw[off : off + sz],
                )
            )
        return cls(entries, filename=filename)

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "DatArchive":
        p = Path(path)
        return cls.from_bytes(p.read_bytes(), filename=p.name)

    def find_entry(self, type_param: int, dest: int) -> DatEntry:
        """Strictly resolves a unique entry by exact (type_param, dest) signature.

        Never falls back to sig4 or size heuristics.
        """
        matches = [
            e for e in self.entries if e.type_param == type_param and e.dest == dest
        ]
        if not matches:
            raise KeyError(
                f"No entry with (type_param={type_param:#x}, dest={dest:#x}) in {self.filename}"
            )
        if len(matches) > 1:
            raise ValueError(
                f"Ambiguous ({len(matches)} matches) for (type_param={type_param:#x}, "
                f"dest={dest:#x}) in {self.filename}"
            )
        return matches[0]

    def find_text_entry(self, dest: int) -> DatEntry:
        """Strictly resolves a text entry by its .psxseg destination (type_param == 0)."""
        if dest not in TEXT_DEST_CEILINGS:
            raise ValueError(f"Destination {dest:#x} is not a known text slot")
        return self.find_entry(TYPE_RAM, dest)

    def find_all_text_entries(self, include_catalog: bool = False) -> List[DatEntry]:
        """Returns all text entries in TOC order (excluding INIT.DAT[7] by default)."""
        result: List[DatEntry] = []
        for e in self.entries:
            if e.type_param == TYPE_RAM and e.dest in TEXT_DEST_CEILINGS:
                if e.dest == CATALOG_DEST and not include_catalog:
                    continue
                result.append(e)
        return result

    def replace_entry(
        self,
        type_param: int,
        dest: int,
        new_data: bytes,
        *,
        allow_catalog: bool = False,
    ) -> int:
        """Replaces a single entry matched strictly by (type_param, dest) with safety checks.

        Enforces:
        - Exact unique (type_param, dest) match.
        - INIT.DAT[7] (dest=0x28000) protection unless allow_catalog=True.
        - .psxseg RAM ceilings for all Type 0 text slots.
        - 4-byte internal section alignment for multi-section text blocks (AB000_00.DAT[1], INIT[7]).
        - Exact glyph-byte stride divisibility for Type 5 PC fonts.
        """
        if not isinstance(new_data, (bytes, bytearray)):
            raise TypeError("new_data must be bytes or bytearray")
        payload = bytes(new_data)
        if not payload:
            raise ValueError("Replacement entry payload cannot be empty")

        entry = self.find_entry(type_param, dest)

        if type_param == TYPE_RAM and dest in TEXT_DEST_CEILINGS:
            if dest == CATALOG_DEST and not allow_catalog:
                raise PermissionError(
                    "Refusing to modify INIT.DAT[7] (dest=0x28000) global item/spell catalog; "
                    "pass allow_catalog=True only if intentionally overriding lock."
                )
            ceiling = TEXT_DEST_CEILINGS[dest]
            if len(payload) > ceiling:
                raise ValueError(
                    f"Payload for {self.filename} dest={dest:#x} is {len(payload)} bytes, "
                    f"exceeding .psxseg ceiling of {ceiling} bytes ({ceiling:#x})"
                )
            if self.filename is not None:
                ms_key = (self.filename.upper(), dest)
                if ms_key in MULTI_SECTION_SPECS:
                    # Validates header offset count, monotonicity, bounds, and 4-byte alignment
                    split_multisection(payload, MULTI_SECTION_SPECS[ms_key])

        elif type_param == TYPE_PC_FONT:
            dim = (dest >> 8) & 0xFF
            if dim == 0 or (dim % 2) != 0:
                raise ValueError(f"Invalid font glyph dimension {dim} in dest={dest:#x}")
            glyph_bytes = (dim * dim) // 2
            if len(payload) % glyph_bytes != 0:
                raise ValueError(
                    f"Font payload length {len(payload)} is not a multiple of "
                    f"{glyph_bytes} B/glyph ({dim}x{dim} 4bpp)"
                )

        entry.data = payload
        entry.size = len(payload)
        return entry.index

    def to_bytes(self) -> bytes:
        """Serializes archive with 1-byte packing, exact entry order, 0 gaps, 0 trailing pad."""
        num_entries = len(self.entries)
        toc_size = num_entries * 16
        out = bytearray(toc_size)
        cur_off = toc_size

        for i, entry in enumerate(self.entries):
            sz = len(entry.data)
            entry.index = i
            entry.offset = cur_off
            entry.size = sz
            struct.pack_into("<4I", out, i * 16, cur_off, sz, entry.type_param, entry.dest)
            cur_off += sz

        for entry in self.entries:
            out.extend(entry.data)

        if len(out) != cur_off:
            raise AssertionError(f"Internal serialization error: {len(out)} != {cur_off}")
        return bytes(out)

    def write_file(self, path: Union[str, Path]) -> None:
        """Writes serialized .DAT bytes to disk."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(self.to_bytes())


def scan_dat_text_entries(
    dat_dir: Union[str, Path], *, include_catalog: bool = False
) -> List[Tuple[str, int, int, int]]:
    """Scans all .DAT files in dat_dir and returns (filename, entry_idx, dest, size) tuples."""
    dpath = Path(dat_dir)
    results: List[Tuple[str, int, int, int]] = []
    for dat_path in sorted(dpath.glob("*.DAT")):
        arc = DatArchive.from_file(dat_path)
        for entry in arc.find_all_text_entries(include_catalog=include_catalog):
            results.append((dat_path.name, entry.index, entry.dest, entry.size))
    return results
