"""Binary text block codec, inline control-tag serializer, and VWF metrics for Breath of Fire IV (PC).

Implements lossless decode/encode for:
- Single-table PC .DAT text entries (typ in {0x0, 0x10000, 0x20000, 0x27000})
- Multi-section uint32 text entries (AB000_00.DAT[1])
- Odd-aligned ptr[0] == 0x201 entries (AREAM005[8], AREAS010[8], AREAS012[8])
- All control opcodes 0x00..0x1F, special font glyphs 0x24..0x87, and native PT-BR accents 0x88..0xA1
- Exact VWF pixel-width measurement from BOF4.exe (+ PT-BR glyph metrics from font_builder)
"""

from __future__ import annotations

import functools
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

DEFAULT_GAME_DIR = Path(
    "/home/mailson/Games/breath-of-fire-iv/drive_c/GOG Games/Breath of Fire IV"
)
DEFAULT_DAT_DIR = DEFAULT_GAME_DIR / "DAT"
DEFAULT_EXE_PATH = DEFAULT_GAME_DIR / "BOF4.exe"

# BOF4.exe raw file offsets for VWF tables (verified against SHA256 a529e1cc...):
# Each entry is 2 bytes: (left_bearing: uint8, advance_width: int8)
VWF_DLG_RAW_OFF = 0x336F3C  # VA 0x0094CD3C: 256 entries indexed by char * 2 (dialogue stepper/drawer)
VWF_16_RAW_OFF = 0x33CFE0   # VA 0x00952DE0: 104 entries indexed by (char - 0x20) * 2 (16x16 slot 0)
VWF_24_RAW_OFF = 0x33D0B0   # VA 0x00952EB0: 104 entries indexed by (char - 0x20) * 2 (24x24 slot 1)

# Shared contract with font_builder / exe_patcher: 26 native PT-BR glyphs at 0x88..0xA1 (glyph IDs 104..129)
PTBR_START_BYTE = 0x88
PTBR_CHARS: List[str] = [
    "á", "à", "â", "ã", "é", "ê", "í", "ó", "ô", "õ", "ú", "ç",
    "Á", "À", "Â", "Ã", "É", "Ê", "Í", "Ó", "Ô", "Õ", "Ú", "Ç",
    "º", "ª",
]
PTBR_CHAR_TO_BYTE: Dict[str, int] = {ch: PTBR_START_BYTE + i for i, ch in enumerate(PTBR_CHARS)}
BYTE_TO_PTBR_CHAR: Dict[int, str] = {PTBR_START_BYTE + i: ch for i, ch in enumerate(PTBR_CHARS)}

# Fallback base ASCII letter per PT-BR char (used only if font_builder metrics are not yet present)
_PTBR_FALLBACK_BASE: Dict[str, str] = {
    "á": "a", "à": "a", "â": "a", "ã": "a",
    "é": "e", "ê": "e", "í": "i",
    "ó": "o", "ô": "o", "õ": "o", "ú": "u", "ç": "c",
    "Á": "A", "À": "A", "Â": "A", "Ã": "A",
    "É": "E", "Ê": "E", "Í": "I",
    "Ó": "O", "Ô": "O", "Õ": "O", "Ú": "U", "Ç": "C",
    "º": "o", "ª": "a",
}

# Exact argument byte count per control opcode 0x00..0x1F (verified in BOF4.exe 0x00527FC0 & 0x00527C30)
OPCODE_ARG_LEN: Dict[int, int] = {
    0x00: 0,  # {END}
    0x01: 0,  # \n
    0x02: 0,  # {PAGE}
    0x03: 0,  # {LEADER}
    0x04: 1,  # {CHAR:XX}
    0x05: 1,  # {COLOR:XX}
    0x06: 0,  # {/COLOR}
    0x07: 1,  # {VAR:XX}
    0x08: 0,  # {NL2}
    0x09: 2,  # {CAT:SS:II} (binary order: 0x09 <idx> <sec>)
    0x0A: 1,  # {SFX:XX}
    0x0B: 0,  # {PAUSE}
    0x0C: 1,  # {WIN:XX}
    0x0D: 0,  # {FX_ON}
    0x0E: 0,  # {FX_OFF}
    0x0F: 1,  # {FX:XX}
    0x10: 1,  # {SPEED:XX}
    0x11: 0,  # {/SPEED}
    0x12: 1,  # {CHOICE_RAW:OO} or combined 0x12 <opt> 0x0C <flags> -> {CHOICE:OO:FF}
    0x13: 1,  # {WAIT:XX}
    0x14: 2,  # {PORTRAIT:A0:A1}
    0x15: 2,  # {SUBMSG:LO:HI}
    0x16: 2,  # {GOTO:LO:HI}
    0x17: 1,  # {COND:XX}
    0x18: 0,  # {OP18}
    0x19: 1,  # {OP19:XX}
    0x1A: 1,  # {KANJI:1A:LL}
    0x1B: 1,  # {KANJI:1B:LL}
    0x1C: 1,  # {KANJI:1C:LL}
    0x1D: 1,  # {KANJI:1D:LL}
    0x1E: 1,  # {KANJI:1E:LL}
    0x1F: 1,  # {KANJI:1F:LL}
}

# Special non-literal printable font glyphs mapped to explicit tags for zero ambiguity
SPECIAL_BYTE_TO_TAG: Dict[int, str] = {
    0x24: "{DOT2}",   # ··
    0x3C: "{LQ}",     # 「
    0x3E: "{RQ}",     # 」
    0x40: "{MDOT}",   # ・
    0x5E: "{WAVE}",   # ~
    0x5F: "{ZENNY}",  # Z (Zenny)
    0x60: "{IV}",     # IV (Roman numeral 4)
    0x7B: "{STAR}",   # ★
    0x7C: "{DEG}",    # °
    0x7D: "{GT}",     # >
    0x7E: "{BTN_0}",
    0x7F: "{BTN_1}",
    0x80: "{BTN_2}",
    0x81: "{BTN_3}",
    0x82: "{BTN_4}",
    0x83: "{BTN_5}",
    0x84: "{BTN_6}",
    0x85: "{BTN_7}",
    0x86: "{BTN_8}",
    0x87: "{BTN_9}",
}
SPECIAL_TAG_TO_BYTE: Dict[str, int] = {tag: b for b, tag in SPECIAL_BYTE_TO_TAG.items()}

# Zero-arg control opcodes mapped directly to fixed tag names
SIMPLE_OPCODE_TO_TAG: Dict[int, str] = {
    0x00: "{END}",
    0x02: "{PAGE}",
    0x03: "{LEADER}",
    0x06: "{/COLOR}",
    0x08: "{NL2}",
    0x0B: "{PAUSE}",
    0x0D: "{FX_ON}",
    0x0E: "{FX_OFF}",
    0x11: "{/SPEED}",
    0x18: "{OP18}",
}
SIMPLE_TAG_TO_OPCODE: Dict[str, int] = {tag: op for op, tag in SIMPLE_OPCODE_TO_TAG.items()}

# 1-byte-argument control opcodes
ONE_ARG_OPCODE_TO_NAME: Dict[int, str] = {
    0x04: "CHAR",
    0x05: "COLOR",
    0x07: "VAR",
    0x0A: "SFX",
    0x0C: "WIN",
    0x0F: "FX",
    0x10: "SPEED",
    0x12: "CHOICE_RAW",
    0x13: "WAIT",
    0x17: "COND",
    0x19: "OP19",
}
ONE_ARG_NAME_TO_OPCODE: Dict[str, int] = {name: op for op, name in ONE_ARG_OPCODE_TO_NAME.items()}

# Safe PT-BR rendering budgets in 320x240 logical pixels and max lines per page
CONTEXT_BUDGETS: Dict[str, Tuple[int, Optional[int]]] = {
    "dialogue_1p": (148, 3),
    "dialogue_2p": (104, 3),
    "dialogue_0p": (195, 3),
    "choice": (140, None),
    "battle_1p": (145, 3),
    "battle_2p": (104, 3),
    "battle_sys": (232, 3),
    "desc": (256, 2),
    "menu": (228, None),
    "init_5": (228, 3),
    "init_6": (154, 3),
}

# Pre-compiled tag matching regexes
_TAG_TOKEN_RE = re.compile(r"\{[^{}]*\}")
_ONE_ARG_RE = re.compile(r"^\{([A-Z0-9_]+):([0-9A-Fa-f]{2})\}$")
_TWO_ARG_RE = re.compile(r"^\{([A-Z0-9_]+):([0-9A-Fa-f]{2}):([0-9A-Fa-f]{2})\}$")


class CodecError(ValueError):
    """Raised when binary text block structure, control tags, or character encoding is invalid."""


@dataclass
class TextSlice:
    """A single unique string slice inside a text section."""

    index: int
    slots: List[int]
    text: str
    terminated: bool = True
    trailing_raw: bytes = b""
    offset: int = 0


@dataclass
class TextSection:
    """A single uint16 pointer-table text section."""

    num_slots: int
    slot_to_slice: List[int]
    slices: List[TextSlice]
    prefix_gap: bytes = b""


@dataclass
class TextBlock:
    """Decoded representation of a PC .DAT text entry (1 or more sections)."""

    sections: List[TextSection]
    is_multi_section: bool = False

    @property
    def section(self) -> TextSection:
        if len(self.sections) != 1:
            raise CodecError(f"Expected single-section block, got {len(self.sections)} sections")
        return self.sections[0]

    @property
    def num_slots(self) -> int:
        return self.section.num_slots

    @property
    def slot_to_slice(self) -> List[int]:
        return self.section.slot_to_slice

    @property
    def slices(self) -> List[TextSlice]:
        return self.section.slices

    @property
    def prefix_gap(self) -> bytes:
        return self.section.prefix_gap


def decode_bytes(raw: bytes, *, ptbr_mode: bool = False) -> str:
    """Decode raw Breath of Fire IV text bytes into a lossless tag-annotated string.

    Args:
        raw: Raw byte sequence from a .DAT text entry.
        ptbr_mode: When False (default, for clean EN DATs), bytes 0x88..0xFF decode as {RAW:XX}
            so leftover Japanese text is never misidentified as PT-BR accents.
            When True (for patched PT-BR DATs), bytes 0x88..0xA1 decode as PTBR_CHARS.
    """
    out: List[str] = []
    i = 0
    n = len(raw)
    while i < n:
        b = raw[i]
        if b == 0x01:
            out.append("\n")
            i += 1
        elif b in SIMPLE_OPCODE_TO_TAG:
            out.append(SIMPLE_OPCODE_TO_TAG[b])
            i += 1
        elif b == 0x12:
            if i + 1 >= n:
                raise CodecError(f"Truncated 0x12 opcode at offset {i}")
            opt = raw[i + 1]
            if i + 3 < n and raw[i + 2] == 0x0C:
                flags = raw[i + 3]
                out.append(f"{{CHOICE:{opt:02X}:{flags:02X}}}")
                i += 4
            else:
                out.append(f"{{CHOICE_RAW:{opt:02X}}}")
                i += 2
        elif b in ONE_ARG_OPCODE_TO_NAME:
            if i + 1 >= n:
                raise CodecError(f"Truncated opcode 0x{b:02X} at offset {i}")
            arg = raw[i + 1]
            out.append(f"{{{ONE_ARG_OPCODE_TO_NAME[b]}:{arg:02X}}}")
            i += 2
        elif b == 0x09:
            if i + 2 >= n:
                raise CodecError(f"Truncated 0x09 opcode at offset {i}")
            item_idx, sec = raw[i + 1], raw[i + 2]
            out.append(f"{{CAT:{sec:02X}:{item_idx:02X}}}")
            i += 3
        elif b == 0x14:
            if i + 2 >= n:
                raise CodecError(f"Truncated 0x14 portrait opcode at offset {i}")
            out.append(f"{{PORTRAIT:{raw[i + 1]:02X}:{raw[i + 2]:02X}}}")
            i += 3
        elif b == 0x15:
            if i + 2 >= n:
                raise CodecError(f"Truncated 0x15 submsg opcode at offset {i}")
            out.append(f"{{SUBMSG:{raw[i + 1]:02X}:{raw[i + 2]:02X}}}")
            i += 3
        elif b == 0x16:
            if i + 2 >= n:
                raise CodecError(f"Truncated 0x16 goto opcode at offset {i}")
            out.append(f"{{GOTO:{raw[i + 1]:02X}:{raw[i + 2]:02X}}}")
            i += 3
        elif 0x1A <= b <= 0x1F:
            if i + 1 >= n:
                raise CodecError(f"Truncated 2-byte kanji escape 0x{b:02X} at offset {i}")
            out.append(f"{{KANJI:{b:02X}:{raw[i + 1]:02X}}}")
            i += 2
        elif b in SPECIAL_BYTE_TO_TAG:
            out.append(SPECIAL_BYTE_TO_TAG[b])
            i += 1
        elif 0x20 <= b <= 0x7A:
            out.append(chr(b))
            i += 1
        elif ptbr_mode and b in BYTE_TO_PTBR_CHAR:
            out.append(BYTE_TO_PTBR_CHAR[b])
            i += 1
        else:
            out.append(f"{{RAW:{b:02X}}}")
            i += 1
    return "".join(out)


def _encode_tag(tag: str, *, allow_raw: bool) -> bytes:
    """Encode a single `{...}` control or special-glyph tag into exact binary bytes."""
    if tag in SIMPLE_TAG_TO_OPCODE:
        return bytes([SIMPLE_TAG_TO_OPCODE[tag]])
    if tag in SPECIAL_TAG_TO_BYTE:
        return bytes([SPECIAL_TAG_TO_BYTE[tag]])

    m1 = _ONE_ARG_RE.match(tag)
    if m1:
        name, hex_val = m1.group(1), m1.group(2)
        val = int(hex_val, 16)
        if name == "RAW":
            if not allow_raw:
                raise CodecError(f"Legacy raw byte tag not allowed in PT-BR text: {tag}")
            return bytes([val])
        if name in ONE_ARG_NAME_TO_OPCODE:
            return bytes([ONE_ARG_NAME_TO_OPCODE[name], val])
        raise CodecError(f"Unknown 1-argument tag: {tag}")

    m2 = _TWO_ARG_RE.match(tag)
    if m2:
        name, h1, h2 = m2.group(1), m2.group(2), m2.group(3)
        v1, v2 = int(h1, 16), int(h2, 16)
        if name == "PORTRAIT":
            return bytes([0x14, v1, v2])
        if name == "GOTO":
            return bytes([0x16, v1, v2])
        if name == "SUBMSG":
            return bytes([0x15, v1, v2])
        if name == "CHOICE":
            return bytes([0x12, v1, 0x0C, v2])
        if name == "CAT":
            # Tag is {CAT:sec:idx}; binary format is 0x09 <idx> <sec>
            return bytes([0x09, v2, v1])
        if name == "KANJI":
            if not allow_raw:
                raise CodecError(f"Legacy Kanji tag not allowed in PT-BR text: {tag}")
            if not (0x1A <= v1 <= 0x1F):
                raise CodecError(f"Invalid Kanji lead byte 0x{v1:02X} in tag: {tag}")
            return bytes([v1, v2])
        raise CodecError(f"Unknown 2-argument tag: {tag}")

    raise CodecError(f"Malformed or unknown tag: {tag}")


def encode_bytes(text: str, *, allow_raw: bool = True) -> bytes:
    """Encode a tag-annotated string into raw Breath of Fire IV bytes.

    Rejects unmapped Unicode characters, malformed/unclosed braces, and ambiguous ASCII punctuation
    that maps to special Capcom font glyphs (use explicit tags like {ZENNY}, {GT}, {DEG}, etc.).
    """
    out = bytearray()
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "{":
            close = text.find("}", i + 1)
            if close == -1:
                raise CodecError(f"Unclosed tag starting at index {i}: {text[i:i+24]!r}")
            tag = text[i : close + 1]
            if "{" in tag[1:]:
                raise CodecError(f"Nested '{{' inside tag at index {i}: {tag!r}")
            out.extend(_encode_tag(tag, allow_raw=allow_raw))
            i = close + 1
        elif ch == "}":
            raise CodecError(f"Stray '}}' at index {i}: {text[max(0, i-8):i+8]!r}")
        elif ch == "\n":
            out.append(0x01)
            i += 1
        elif ch in PTBR_CHAR_TO_BYTE:
            out.append(PTBR_CHAR_TO_BYTE[ch])
            i += 1
        else:
            code = ord(ch)
            if 0x20 <= code <= 0x7A and code not in SPECIAL_BYTE_TO_TAG:
                out.append(code)
                i += 1
            else:
                hint = ""
                if code in SPECIAL_BYTE_TO_TAG:
                    hint = f" (use explicit tag {SPECIAL_BYTE_TO_TAG[code]} instead)"
                raise CodecError(
                    f"Unmapped character {ch!r} (U+{code:04X}) at index {i}{hint}"
                )
    return bytes(out)


def encode_ptbr_string(text: str) -> bytes:
    """Encode a PT-BR string strictly: rejects unmapped Unicode chars and legacy {RAW}/{KANJI} tags."""
    return encode_bytes(text, allow_raw=False)


def _find_first_null_opcode(raw: bytes) -> int:
    """Return byte index of the first 0x00 opcode in raw, or -1 if none."""
    i = 0
    n = len(raw)
    while i < n:
        b = raw[i]
        if b == 0x00:
            return i
        if b < 0x20:
            al = OPCODE_ARG_LEN[b]
            if i + 1 + al > n:
                raise CodecError(f"Truncated control opcode 0x{b:02X} at byte {i}")
            i += 1 + al
        else:
            i += 1
    return -1


def decode_slice(raw: bytes, *, ptbr_mode: bool = False) -> Tuple[str, bool, bytes]:
    """Decode one string slice into (text, terminated, trailing_raw).

    Splits at the first 0x00 opcode so translators never see trailing null terminators or dead
    padding/orphaned bytes after 0x00, while retaining 100% byte-exact round-trip fidelity.
    """
    null_pos = _find_first_null_opcode(raw)
    if null_pos == -1:
        return decode_bytes(raw, ptbr_mode=ptbr_mode), False, b""
    active = raw[:null_pos]
    trailing = raw[null_pos + 1 :]
    return decode_bytes(active, ptbr_mode=ptbr_mode), True, trailing


def encode_slice(
    text: str,
    *,
    terminated: bool = True,
    trailing_raw: bytes = b"",
    allow_raw: bool = True,
) -> bytes:
    """Encode one string slice back to binary bytes."""
    body = encode_bytes(text, allow_raw=allow_raw)
    if terminated:
        return body + b"\x00" + trailing_raw
    return body + trailing_raw


def _looks_like_multi_section(raw: bytes) -> bool:
    """Detect uint32 multi-section text blocks (e.g., AB000_00.DAT[1]: [0x08, 0x2E3C])."""
    if len(raw) < 16:
        return False
    sec0 = struct.unpack_from("<I", raw, 0)[0]
    if sec0 < 8 or sec0 % 4 != 0 or sec0 >= len(raw):
        return False
    n_secs = sec0 // 4
    if n_secs > 16:
        return False
    offsets = struct.unpack_from(f"<{n_secs}I", raw, 0)
    # In a single-table uint16 header, bytes [2:4] are ptr[1] >= ptr[0] >= 2 (never 0).
    # In a uint32 section header, sec0 < 0x100 implies bytes [2:4] == 0x0000.
    if not all(offsets[i] < offsets[i + 1] < len(raw) for i in range(n_secs - 1)):
        return False
    if any(off % 4 != 0 for off in offsets):
        return False
    # Verify each section starts with a plausible uint16 pointer table
    for idx, so in enumerate(offsets):
        se = offsets[idx + 1] if idx + 1 < n_secs else len(raw)
        if se - so < 4:
            return False
        p0 = struct.unpack_from("<H", raw, so)[0] & ~1
        if p0 < 2 or p0 >= (se - so):
            return False
    return True


def _decode_section(raw: bytes, *, ptbr_mode: bool = False) -> TextSection:
    if len(raw) < 2:
        raise CodecError(f"Text section too short ({len(raw)} bytes)")
    first_ptr = struct.unpack_from("<H", raw, 0)[0]
    hdr_sz = first_ptr & ~1  # Handles odd ptr[0] == 0x201 in AREAM005/AREAS010/AREAS012
    if hdr_sz < 2 or hdr_sz > len(raw):
        raise CodecError(f"Invalid pointer table header size 0x{hdr_sz:X} (len=0x{len(raw):X})")

    num_slots = hdr_sz // 2
    ptrs = list(struct.unpack_from(f"<{num_slots}H", raw, 0))
    uniq_offsets = sorted(set(ptrs))
    if uniq_offsets[0] < hdr_sz or uniq_offsets[-1] >= len(raw):
        raise CodecError(
            f"Pointer out of bounds: min=0x{uniq_offsets[0]:X} max=0x{uniq_offsets[-1]:X} "
            f"hdr=0x{hdr_sz:X} len=0x{len(raw):X}"
        )

    prefix_gap = raw[hdr_sz : uniq_offsets[0]]
    offset_to_slice_idx = {off: idx for idx, off in enumerate(uniq_offsets)}
    slot_to_slice = [offset_to_slice_idx[p] for p in ptrs]

    slice_slots: List[List[int]] = [[] for _ in uniq_offsets]
    for slot_idx, s_idx in enumerate(slot_to_slice):
        slice_slots[s_idx].append(slot_idx)

    slices: List[TextSlice] = []
    for k, st in enumerate(uniq_offsets):
        en = uniq_offsets[k + 1] if k + 1 < len(uniq_offsets) else len(raw)
        text, terminated, trailing_raw = decode_slice(raw[st:en], ptbr_mode=ptbr_mode)
        slices.append(
            TextSlice(
                index=k,
                slots=slice_slots[k],
                text=text,
                terminated=terminated,
                trailing_raw=trailing_raw,
                offset=st,
            )
        )

    return TextSection(
        num_slots=num_slots,
        slot_to_slice=slot_to_slice,
        slices=slices,
        prefix_gap=prefix_gap,
    )


def _encode_section(
    section: TextSection,
    *,
    realign_odd_prefix: bool = False,
    strip_dead_trailing: bool = False,
    allow_raw: bool = True,
) -> bytes:
    hdr_sz = section.num_slots * 2
    prefix = b"" if realign_odd_prefix else section.prefix_gap
    payload = bytearray(prefix)
    slice_offsets: List[int] = []

    for sl in section.slices:
        off = hdr_sz + len(payload)
        if off > 0xFFFF:
            raise CodecError(
                f"Text section offset 0x{off:X} exceeds uint16 maximum (0xFFFF) at slice {sl.index}"
            )
        slice_offsets.append(off)
        trailing = b"" if strip_dead_trailing else sl.trailing_raw
        payload.extend(
            encode_slice(
                sl.text,
                terminated=sl.terminated,
                trailing_raw=trailing,
                allow_raw=allow_raw,
            )
        )

    if len(section.slot_to_slice) != section.num_slots:
        raise CodecError(
            f"slot_to_slice length ({len(section.slot_to_slice)}) != num_slots ({section.num_slots})"
        )

    hdr = bytearray(hdr_sz)
    for slot_idx, s_idx in enumerate(section.slot_to_slice):
        struct.pack_into("<H", hdr, slot_idx * 2, slice_offsets[s_idx])
    return bytes(hdr) + bytes(payload)


def decode_text_block(
    raw: bytes,
    *,
    multi_section: Optional[bool] = None,
    ptbr_mode: bool = False,
) -> TextBlock:
    """Decode a PC .DAT text block (single-table or multi-section uint32) into a TextBlock."""
    is_multi = _looks_like_multi_section(raw) if multi_section is None else multi_section
    if not is_multi:
        return TextBlock(sections=[_decode_section(raw, ptbr_mode=ptbr_mode)], is_multi_section=False)

    sec0 = struct.unpack_from("<I", raw, 0)[0]
    n_secs = sec0 // 4
    offsets = list(struct.unpack_from(f"<{n_secs}I", raw, 0))
    sections: List[TextSection] = []
    for idx, so in enumerate(offsets):
        se = offsets[idx + 1] if idx + 1 < n_secs else len(raw)
        sections.append(_decode_section(raw[so:se], ptbr_mode=ptbr_mode))
    return TextBlock(sections=sections, is_multi_section=True)


def encode_text_block(
    block: TextBlock,
    *,
    realign_odd_prefix: bool = False,
    strip_dead_trailing: bool = False,
    allow_raw: bool = True,
) -> bytes:
    """Encode a TextBlock back into raw PC .DAT entry bytes."""
    if not block.is_multi_section:
        if len(block.sections) != 1:
            raise CodecError("Single-section TextBlock must contain exactly 1 section")
        return _encode_section(
            block.sections[0],
            realign_odd_prefix=realign_odd_prefix,
            strip_dead_trailing=strip_dead_trailing,
            allow_raw=allow_raw,
        )

    n_secs = len(block.sections)
    header_sz = n_secs * 4
    body = bytearray()
    sec_offsets: List[int] = []
    for idx, sec in enumerate(block.sections):
        sec_offsets.append(header_sz + len(body))
        encoded = _encode_section(
            sec,
            realign_odd_prefix=realign_odd_prefix,
            strip_dead_trailing=strip_dead_trailing,
            allow_raw=allow_raw,
        )
        body.extend(encoded)
        # Keep non-final section starts 4-byte aligned (required for uint32 section header tables)
        if idx + 1 < n_secs:
            rem = len(body) % 4
            if rem != 0:
                body.extend(b"\x00" * (4 - rem))

    hdr = struct.pack(f"<{n_secs}I", *sec_offsets)
    return hdr + bytes(body)


def extract_tags(text: str) -> List[str]:
    """Return ordered list of all `{...}` control and special-glyph tags in text."""
    return _TAG_TOKEN_RE.findall(text)


def has_legacy_jp(text: str) -> bool:
    """Return True if text contains leftover Japanese byte/kanji tags ({KANJI:...}, {RAW:...}, {OP19:...})."""
    for tag in extract_tags(text):
        if tag.startswith(("{KANJI:", "{RAW:", "{OP19:")):
            return True
    return False


def count_portraits(text: str) -> int:
    """Return the peak number of simultaneously active portrait slots (0..4) in text."""
    active: set[int] = set()
    peak = 0
    for tag in extract_tags(text):
        if tag.startswith("{PORTRAIT:"):
            m = _TWO_ARG_RE.match(tag)
            if not m:
                continue
            a0, a1 = int(m.group(2), 16), int(m.group(3), 16)
            if a0 == 0xFF and a1 == 0xFF:
                active.clear()
            else:
                active.add(a1 >> 6)
                if len(active) > peak:
                    peak = len(active)
    return peak


def _load_font_builder_metrics() -> Optional[Tuple[Dict[int, Tuple[int, int]], Dict[int, Tuple[int, int]]]]:
    """Attempt lazy import of PTBR_VWF_24 and PTBR_VWF_16 from bof4_ptbr.font_builder."""
    try:
        from bof4_ptbr import font_builder  # type: ignore
    except ImportError:
        return None
    if hasattr(font_builder, "get_ptbr_vwf_metrics"):
        res = font_builder.get_ptbr_vwf_metrics()
        if isinstance(res, dict) and "vwf_24" in res and "vwf_16" in res:
            return res["vwf_24"], res["vwf_16"]
        if isinstance(res, tuple) and len(res) == 2:
            return res[0], res[1]
    vwf24 = getattr(font_builder, "PTBR_VWF_24", None)
    vwf16 = getattr(font_builder, "PTBR_VWF_16", None)
    if vwf24 and vwf16:
        return vwf24, vwf16
    return None


@functools.lru_cache(maxsize=4)
def _load_vanilla_vwf_from_exe(exe_path_str: str) -> Tuple[
    Dict[int, Tuple[int, int]],
    Dict[int, Tuple[int, int]],
    Dict[int, Tuple[int, int]],
]:
    data = Path(exe_path_str).read_bytes()
    vwf_dlg: Dict[int, Tuple[int, int]] = {}
    for ch in range(0x100):
        b0 = data[VWF_DLG_RAW_OFF + ch * 2]
        b1 = struct.unpack_from("b", data, VWF_DLG_RAW_OFF + ch * 2 + 1)[0]
        vwf_dlg[ch] = (b0, b1)

    vwf_16: Dict[int, Tuple[int, int]] = {}
    vwf_24: Dict[int, Tuple[int, int]] = {}
    for idx in range(104):  # 0x20..0x87
        ch = 0x20 + idx
        b0_16 = data[VWF_16_RAW_OFF + idx * 2]
        b1_16 = struct.unpack_from("b", data, VWF_16_RAW_OFF + idx * 2 + 1)[0]
        vwf_16[ch] = (b0_16, b1_16)

        b0_24 = data[VWF_24_RAW_OFF + idx * 2]
        b1_24 = struct.unpack_from("b", data, VWF_24_RAW_OFF + idx * 2 + 1)[0]
        vwf_24[ch] = (b0_24, b1_24)

    return vwf_24, vwf_16, vwf_dlg


def load_vwf_tables(
    exe_path: str | Path = DEFAULT_EXE_PATH,
) -> Dict[str, Dict[int, Tuple[int, int]]]:
    """Load vanilla VWF_24, VWF_16, and VWF_dlg tables from BOF4.exe merged with PT-BR 0x88..0xA1 metrics.

    Returns dict with keys `"vwf_24"`, `"vwf_16"`, `"vwf_dlg"`, each mapping
    `byte_code -> (left_bearing, advance_width)` in native font pixel units (24px or 16px).
    """
    base_24, base_16, base_dlg = _load_vanilla_vwf_from_exe(str(Path(exe_path).resolve()))
    vwf_24 = dict(base_24)
    vwf_16 = dict(base_16)
    vwf_dlg = dict(base_dlg)

    fb = _load_font_builder_metrics()
    if fb is not None:
        ptbr_24, ptbr_16 = fb
        for b, metrics in ptbr_24.items():
            vwf_24[b] = tuple(metrics)
            vwf_dlg[b] = tuple(metrics)
        for b, metrics in ptbr_16.items():
            vwf_16[b] = tuple(metrics)
    else:
        for ch, b in PTBR_CHAR_TO_BYTE.items():
            base_ord = ord(_PTBR_FALLBACK_BASE[ch])
            vwf_24[b] = vwf_24[base_ord]
            vwf_dlg[b] = vwf_24[base_ord]
            vwf_16[b] = vwf_16[base_ord]

    return {"vwf_24": vwf_24, "vwf_16": vwf_16, "vwf_dlg": vwf_dlg}


def _tokenize_for_layout(text: str) -> List[Tuple[str, str]]:
    """Split text into ('tag', '{...}'), ('nl', '\\n'), or ('char', ch) tokens."""
    tokens: List[Tuple[str, str]] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "{":
            close = text.find("}", i + 1)
            if close == -1:
                raise CodecError(f"Unclosed tag at index {i}")
            tokens.append(("tag", text[i : close + 1]))
            i = close + 1
        elif ch == "\n":
            tokens.append(("nl", "\n"))
            i += 1
        else:
            tokens.append(("char", ch))
            i += 1
    return tokens


def measure_line_px(
    text: str,
    font_slot: int = 1,
    *,
    vwf_tables: Optional[Dict[str, Dict[int, Tuple[int, int]]]] = None,
    var_px: int = 28,
    char_name_px: int = 28,
    item_name_px: int = 52,
    btn_px: int = 12,
) -> int:
    """Measure the exact logical width (in 320x240 px) of a single rendered line.

    Matches BOF4.exe `0x00527ECB` / `0x006297C6` (`int(advance_width * 0.5)` per character).
    Zero-width control tags ({WIN}, {PORTRAIT}, {COLOR}, {/COLOR}, {SFX}, etc.) add 0 px.
    Runtime substitution tags ({CHAR}, {LEADER}, {VAR}, {CAT}, {BTN_0..9}) add conservative estimates.
    """
    tables = vwf_tables if vwf_tables is not None else load_vwf_tables()
    table = tables["vwf_24"] if font_slot == 1 else tables["vwf_16"]
    total = 0
    for kind, val in _tokenize_for_layout(text):
        if kind == "nl":
            continue
        if kind == "tag":
            if val in SPECIAL_TAG_TO_BYTE:
                b = SPECIAL_TAG_TO_BYTE[val]
                if 0x7E <= b <= 0x87:
                    total += btn_px
                else:
                    adv = table.get(b, (0, 16))[1]
                    total += int(adv * 0.5)
            elif val == "{LEADER}" or val.startswith("{CHAR:"):
                total += char_name_px
            elif val.startswith("{VAR:"):
                total += var_px
            elif val.startswith("{CAT:"):
                total += item_name_px
            # All other control tags (WIN, PORTRAIT, COLOR, SFX, PAUSE, WAIT, FX, SPEED, GOTO, ...) are 0 px
            continue
        # Printable character
        if val == " ":
            # Both 16px (0x629A20: add edi, 8) and 24px (0x6295E6: fadd 8.0 / VWF_24[0x20]=16*0.5)
            # advance ASCII space by exactly 8 logical pixels.
            total += 8
            continue
        if val in PTBR_CHAR_TO_BYTE:
            b = PTBR_CHAR_TO_BYTE[val]
        else:
            b = ord(val)
        adv = table.get(b, (0, 16))[1]
        total += int(adv * 0.5)
    return total


def split_pages_and_lines(text: str) -> List[Dict[str, object]]:
    """Split a tag-annotated string into rendered pages/boxes and their individual lines.

    Each returned item is:
        {
            "is_choice": bool,
            "choice_tag": Optional[str],
            "declared_choices": Optional[int],
            "lines": List[str],          # visual lines (split on \\n and {NL2})
            "choice_items": List[str],   # selectable choice options (split ONLY on \\n)
        }
    """
    pages: List[Dict[str, object]] = []
    cur_lines: List[str] = []
    cur_buf: List[str] = []
    cur_choice_items: List[str] = []
    cur_choice_buf: List[str] = []
    is_choice = False
    choice_tag: Optional[str] = None
    declared_choices: Optional[int] = None

    def flush_page() -> None:
        nonlocal cur_lines, cur_buf, cur_choice_items, cur_choice_buf
        nonlocal is_choice, choice_tag, declared_choices
        cur_lines.append("".join(cur_buf))
        if is_choice:
            cur_choice_items.append("".join(cur_choice_buf))
        pages.append(
            {
                "is_choice": is_choice,
                "choice_tag": choice_tag,
                "declared_choices": declared_choices,
                "lines": cur_lines,
                "choice_items": cur_choice_items if is_choice else [],
            }
        )
        cur_lines = []
        cur_buf = []
        cur_choice_items = []
        cur_choice_buf = []
        is_choice = False
        choice_tag = None
        declared_choices = None

    for kind, val in _tokenize_for_layout(text):
        if kind == "nl":
            cur_lines.append("".join(cur_buf))
            cur_buf = []
            if is_choice:
                cur_choice_items.append("".join(cur_choice_buf))
                cur_choice_buf = []
        elif kind == "tag" and val == "{NL2}":
            # Visual continuation wrap ONLY: does not start a new selectable choice option.
            cur_lines.append("".join(cur_buf))
            cur_buf = []
            if is_choice:
                cur_choice_buf.append(val)
        elif kind == "tag" and val == "{PAGE}":
            flush_page()
        elif kind == "tag" and (val.startswith("{CHOICE:") or val.startswith("{CHOICE_RAW:")):
            # Prompt ends before choice box starts
            if cur_lines or any(tok.strip() for tok in cur_buf):
                flush_page()
            else:
                cur_lines = []
                cur_buf = []
                cur_choice_items = []
                cur_choice_buf = []
            is_choice = True
            choice_tag = val
            m2 = _TWO_ARG_RE.match(val)
            if m2:
                flags = int(m2.group(3), 16)
                cnt = flags & 0x0F
                declared_choices = cnt if cnt > 0 else None
        else:
            cur_buf.append(val)
            if is_choice:
                cur_choice_buf.append(val)

    if cur_lines or cur_buf or is_choice:
        flush_page()
    return pages


def _wrap_single_page(
    page_text: str,
    max_px: int,
    *,
    font_slot: int,
    vwf_tables: Dict[str, Dict[int, Tuple[int, int]]],
) -> List[str]:
    """Wrap one page's text at word boundaries without ever splitting inside a `{...}` tag."""
    tokens = _tokenize_for_layout(page_text)
    # Collapse existing newlines to spaces while keeping leading/inline tags glued to adjacent words
    atoms: List[str] = []
    cur: List[str] = []
    leading_tags: List[str] = []
    seen_visible = False

    def is_visible_token(kind: str, val: str) -> bool:
        if kind == "char":
            return not val.isspace()
        if kind == "tag":
            return (
                val in SPECIAL_TAG_TO_BYTE
                or val == "{LEADER}"
                or val.startswith(("{CHAR:", "{VAR:", "{CAT:"))
            )
        return False

    for kind, val in tokens:
        if kind == "nl" or (kind == "char" and val == " "):
            if cur:
                atoms.append("".join(cur))
                cur = []
            continue
        if not seen_visible and kind == "tag" and not is_visible_token(kind, val):
            leading_tags.append(val)
            continue
        seen_visible = True
        cur.append(val)

    if cur:
        atoms.append("".join(cur))

    prefix = "".join(leading_tags)
    if not atoms:
        return [prefix] if prefix else [""]

    lines: List[str] = []
    current = prefix + atoms[0]
    for word in atoms[1:]:
        candidate = current + " " + word
        if measure_line_px(candidate, font_slot=font_slot, vwf_tables=vwf_tables) <= max_px:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def wrap_dialogue_text(
    text: str,
    max_px: int,
    *,
    max_lines_per_page: int = 3,
    font_slot: int = 1,
    vwf_tables: Optional[Dict[str, Dict[int, Tuple[int, int]]]] = None,
    auto_paginate: bool = True,
) -> str:
    """Tag-preserving smart wrapper for PT-BR dialogue strings.

    Preserves all `{...}` control codes, existing `{PAGE}` breaks, and `{CHOICE:...}` blocks
    verbatim while re-wrapping prose lines to fit `<= max_px`. If `auto_paginate` is True and
    a wrapped prose page exceeds `max_lines_per_page`, splits overflow lines onto new `{PAGE}`s.
    """
    tables = vwf_tables if vwf_tables is not None else load_vwf_tables()

    # Preserve trailing {CHOICE:...}, {GOTO:...}, or {SUBMSG:...} suffix untouched if present
    suffix_match = re.search(
        r"((?:\n?\{(?:GOTO|SUBMSG):[^{}]+\}|\{CHOICE(?:_RAW)?:[^{}]+\}.*))$",
        text,
        flags=re.DOTALL,
    )
    if suffix_match:
        head = text[: suffix_match.start()]
        tail = suffix_match.group(1)
    else:
        head = text
        tail = ""

    raw_pages = head.split("{PAGE}") if head else []
    rebuilt_pages: List[str] = []
    for raw_page in raw_pages:
        wrapped_lines = _wrap_single_page(raw_page, max_px, font_slot=font_slot, vwf_tables=tables)
        if auto_paginate and max_lines_per_page and len(wrapped_lines) > max_lines_per_page:
            for idx in range(0, len(wrapped_lines), max_lines_per_page):
                rebuilt_pages.append("\n".join(wrapped_lines[idx : idx + max_lines_per_page]))
        else:
            rebuilt_pages.append("\n".join(wrapped_lines))

    return "{PAGE}".join(rebuilt_pages) + tail
