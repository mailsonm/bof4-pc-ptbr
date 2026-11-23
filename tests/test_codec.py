"""Unit & corpus round-trip tests for bof4_ptbr.codec and bof4_ptbr.validate."""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bof4_ptbr.codec import (
    BYTE_TO_PTBR_CHAR,
    DEFAULT_DAT_DIR,
    DEFAULT_EXE_PATH,
    PTBR_CHAR_TO_BYTE,
    PTBR_CHARS,
    CodecError,
    count_portraits,
    decode_bytes,
    decode_text_block,
    encode_bytes,
    encode_ptbr_string,
    encode_text_block,
    extract_tags,
    load_vwf_tables,
    measure_line_px,
    wrap_dialogue_text,
)
from bof4_ptbr.validate import validate_entry, validate_shard

CLEAN_DAT_DIR = Path(DEFAULT_DAT_DIR)
CLEAN_EXE_PATH = Path(DEFAULT_EXE_PATH)


def _iter_all_400_clean_text_blocks():
    """Yield (filename, entry_idx, typ, raw_bytes) for all 400 non-INIT[7] DAT text blocks."""
    for fp in sorted(CLEAN_DAT_DIR.glob("*.DAT")):
        data = fp.read_bytes()
        if len(data) < 16:
            continue
        first_off = struct.unpack_from("<I", data, 0)[0]
        if first_off == 0 or first_off % 16 != 0 or first_off > len(data):
            continue
        for idx in range(first_off // 16):
            off, sz, addr, typ = struct.unpack_from("<4I", data, idx * 16)
            if addr == 0 and typ in (0x0, 0x10000, 0x20000, 0x27000) and sz > 0:
                yield fp.name, idx, typ, data[off : off + sz]


class TestCodecControlTags(unittest.TestCase):
    """Test inline tag bijectivity, PT-BR encoding, and error rejection."""

    def test_ptbr_char_table_contract(self):
        self.assertEqual(len(PTBR_CHARS), 26)
        self.assertEqual(PTBR_CHAR_TO_BYTE["á"], 0x88)
        self.assertEqual(PTBR_CHAR_TO_BYTE["ç"], 0x93)
        self.assertEqual(PTBR_CHAR_TO_BYTE["Á"], 0x94)
        self.assertEqual(PTBR_CHAR_TO_BYTE["Ç"], 0x9F)
        self.assertEqual(PTBR_CHAR_TO_BYTE["º"], 0xA0)
        self.assertEqual(PTBR_CHAR_TO_BYTE["ª"], 0xA1)
        for idx, ch in enumerate(PTBR_CHARS):
            self.assertEqual(BYTE_TO_PTBR_CHAR[0x88 + idx], ch)

    def test_all_control_opcodes_roundtrip(self):
        raw = bytes(
            [
                0x0C, 0x04,              # {WIN:04}
                0x14, 0xC2, 0x40,        # {PORTRAIT:C2:40} (arg1 == '@' must NOT corrupt!)
                0x05, 0x02,              # {COLOR:02}
                0x03,                    # {LEADER}
                0x04, 0x05,              # {CHAR:05}
                0x06,                    # {/COLOR}
                0x01,                    # \n
                0x07, 0x00,              # {VAR:00}
                0x08,                    # {NL2}
                0x09, 0xEF, 0x04,        # {CAT:04:EF} (sec=04, idx=EF)
                0x0A, 0x06,              # {SFX:06}
                0x0B,                    # {PAUSE}
                0x0D,                    # {FX_ON}
                0x0F, 0x02,              # {FX:02}
                0x0E,                    # {FX_OFF}
                0x10, 0x02,              # {SPEED:02}
                0x11,                    # {/SPEED}
                0x13, 0x45,              # {WAIT:45}
                0x02,                    # {PAGE}
                0x12, 0x82, 0x0C, 0x82,  # {CHOICE:82:82}
                ord("Y"), ord("e"), ord("s"), 0x01, ord("N"), ord("o"),
                0x15, 0x41, 0x00,        # {SUBMSG:41:00}
                0x16, 0x16, 0x40,        # {GOTO:16:40}
                0x17, 0x01,              # {COND:01}
                0x18,                    # {OP18}
                0x19, 0x00,              # {OP19:00}
                0x1A, 0xD7,              # {KANJI:1A:D7}
                0x00,                    # {END}
            ]
        )
        decoded = decode_bytes(raw)
        self.assertIn("{WIN:04}", decoded)
        self.assertIn("{PORTRAIT:C2:40}", decoded)
        self.assertIn("{CAT:04:EF}", decoded)
        self.assertIn("{CHOICE:82:82}", decoded)
        self.assertIn("{GOTO:16:40}", decoded)
        self.assertIn("{KANJI:1A:D7}", decoded)
        self.assertEqual(encode_bytes(decoded), raw)

    def test_choice_without_0c_uses_choice_raw(self):
        raw = b"\x12\x00Yes\x01No\x00"
        decoded = decode_bytes(raw)
        self.assertEqual(decoded, "{CHOICE_RAW:00}Yes\nNo{END}")
        self.assertEqual(encode_bytes(decoded), raw)

    def test_special_glyphs_roundtrip(self):
        raw = bytes([0x24, 0x3C, 0x3E, 0x40, 0x5E, 0x5F, 0x60, 0x7B, 0x7C, 0x7D, 0x7E, 0x87])
        decoded = decode_bytes(raw)
        self.assertEqual(
            decoded,
            "{DOT2}{LQ}{RQ}{MDOT}{WAVE}{ZENNY}{IV}{STAR}{DEG}{GT}{BTN_0}{BTN_9}",
        )
        self.assertEqual(encode_bytes(decoded), raw)

    def test_ptbr_accent_encode_and_decode_modes(self):
        text = '{WIN:04}{PORTRAIT:C2:40}"Olá! Você é o {CHAR:00}? Coração, ação, 1º lugar!"'
        raw = encode_ptbr_string(text)
        # Verify byte 0x40 in portrait arg was NOT touched, and accents encoded to 0x88..0xA1
        self.assertTrue(raw.startswith(b"\x0c\x04\x14\xc2@\"Ol\x88! Voc\x8d \x8c o \x04\x00?"))
        self.assertIn(bytes([PTBR_CHAR_TO_BYTE["ç"], PTBR_CHAR_TO_BYTE["ã"]]), raw)
        self.assertIn(bytes([PTBR_CHAR_TO_BYTE["º"]]), raw)
        # In ptbr_mode=True, accents round-trip back to Unicode PT-BR
        self.assertEqual(decode_bytes(raw, ptbr_mode=True), text)
        # In ptbr_mode=False (clean EN mode), 0x88..0xFF decode as {RAW:xx}
        self.assertIn("{RAW:88}", decode_bytes(raw, ptbr_mode=False))

    def test_unmapped_characters_and_bad_tags_rejected(self):
        for bad in [
            "über",           # unmapped umlaut
            "“Olá”",          # smart quotes
            "Ryu — Nina",     # em-dash
            "{PORTRAIT:ZZ}",  # malformed tag
            "{UNKNOWN_TAG}",  # unknown tag
            "unclosed {COLOR:02",
            "stray } brace",
            "raw jp {RAW:89}",  # encode_ptbr_string rejects {RAW:...}
        ]:
            with self.assertRaises(CodecError, msg=f"Should reject {bad!r}"):
                encode_ptbr_string(bad)

    def test_portrait_counting(self):
        self.assertEqual(count_portraits("Just narration."), 0)
        self.assertEqual(count_portraits("{PORTRAIT:41:00}One left."), 1)
        self.assertEqual(count_portraits("{PORTRAIT:C2:40}One right."), 1)
        self.assertEqual(
            count_portraits("{PORTRAIT:41:00}Left{PAGE}{PORTRAIT:81:40}And right."),
            2,
        )
        self.assertEqual(
            count_portraits("{PORTRAIT:41:00}Left{PORTRAIT:FF:FF}Cleared."),
            1,  # peak concurrent portraits was 1
        )


class TestAll400CleanDatRoundTrip(unittest.TestCase):
    """Exhaustive byte-exact round-trip test across ALL 400 clean English DAT text blocks."""

    def test_all_400_text_blocks_byte_exact_roundtrip(self):
        self.assertTrue(CLEAN_DAT_DIR.is_dir(), f"Missing clean DAT dir: {CLEAN_DAT_DIR}")
        blocks = list(_iter_all_400_clean_text_blocks())
        self.assertEqual(len(blocks), 400, f"Expected 400 text entries, found {len(blocks)}")

        mismatches = []
        odd_prefix_files = []
        multi_section_files = []

        for fn, idx, typ, raw in blocks:
            block = decode_text_block(raw)
            if block.is_multi_section:
                multi_section_files.append((fn, idx))
            if any(sec.prefix_gap for sec in block.sections):
                odd_prefix_files.append((fn, idx))
            rebuilt = encode_text_block(block)
            if rebuilt != raw:
                # Find first differing byte for diagnostics
                first_diff = next(
                    (i for i in range(min(len(raw), len(rebuilt))) if raw[i] != rebuilt[i]),
                    min(len(raw), len(rebuilt)),
                )
                mismatches.append((fn, idx, len(raw), len(rebuilt), first_diff))

        self.assertEqual(mismatches, [], f"Round-trip mismatches (showing up to 5): {mismatches[:5]}")
        self.assertEqual(multi_section_files, [("AB000_00.DAT", 1)])
        self.assertEqual(
            sorted(odd_prefix_files),
            [("AREAM005.DAT", 8), ("AREAS010.DAT", 8), ("AREAS012.DAT", 8)],
        )

    def test_odd_prefix_realign_for_ptbr(self):
        data = (CLEAN_DAT_DIR / "AREAM005.DAT").read_bytes()
        off, sz, addr, typ = struct.unpack_from("<4I", data, 8 * 16)
        raw = data[off : off + sz]
        block = decode_text_block(raw)
        self.assertEqual(block.prefix_gap, b"6")
        realigned = encode_text_block(block, realign_odd_prefix=True)
        first_ptr = struct.unpack_from("<H", realigned, 0)[0]
        self.assertEqual(first_ptr, 0x200)
        self.assertEqual(len(realigned), len(raw) - 1)


class TestVwfAndWrapper(unittest.TestCase):
    """Test VWF pixel measurement against BOF4.exe tables and smart dialogue wrapping."""

    def test_vwf_tables_loaded_from_clean_exe(self):
        self.assertTrue(CLEAN_EXE_PATH.is_file())
        tables = load_vwf_tables(CLEAN_EXE_PATH)
        # Known exact widths from BOF4.exe disassembly (#7):
        # 24px: ' ' = 16, '!' = 8, 'i' = 8, 'W' = 23, 'M' = 21
        self.assertEqual(tables["vwf_24"][ord(" ")][1], 16)
        self.assertEqual(tables["vwf_24"][ord("!")][1], 8)
        self.assertEqual(tables["vwf_24"][ord("i")][1], 8)
        self.assertEqual(tables["vwf_24"][ord("W")][1], 23)
        self.assertEqual(tables["vwf_24"][ord("M")][1], 21)
        # 16px: ' ' raw table is 0 (0x629A20 hardcodes space += 8 logical px), 'i' = 6, 'W' = 16
        self.assertEqual(tables["vwf_16"][ord(" ")][1], 0)
        self.assertEqual(tables["vwf_16"][ord("i")][1], 6)
        self.assertEqual(tables["vwf_16"][ord("W")][1], 16)
        self.assertEqual(measure_line_px(" ", font_slot=0), 8)
        self.assertEqual(measure_line_px(" ", font_slot=1), 8)
        # All 26 PT-BR chars must match font_builder's exact VWF metrics (when available)
        from bof4_ptbr.font_builder import PTBR_VWF_16, PTBR_VWF_24

        for b in range(0x88, 0xA2):
            self.assertEqual(tables["vwf_24"][b], PTBR_VWF_24[b])
            self.assertEqual(tables["vwf_dlg"][b], PTBR_VWF_24[b])
            self.assertEqual(tables["vwf_16"][b], PTBR_VWF_16[b])

    def test_measure_line_px_ignores_zero_width_tags_and_counts_accents(self):
        plain = measure_line_px("Olá, você!")
        tagged = measure_line_px("{WIN:04}{PORTRAIT:C2:40}{COLOR:02}Olá, você!{/COLOR}")
        self.assertEqual(plain, tagged)
        # "WW" = 2 * int(23 * 0.5) = 22 px in 320px logical space
        self.assertEqual(measure_line_px("WW", font_slot=1), 22)
        self.assertEqual(measure_line_px("ii", font_slot=1), 8)

    def test_wrap_dialogue_text_preserves_tags_and_fits_budget(self):
        src = (
            '{WIN:04}{PORTRAIT:C2:40}"Ouvi dizer que havia muita gente '
            'trabalhando por aqui, mas não vejo ninguém!"'
        )
        wrapped = wrap_dialogue_text(src, max_px=148)
        # Auto-pagination inserts {PAGE} after 3 lines while keeping all original tags in exact order
        self.assertEqual([t for t in extract_tags(wrapped) if t != "{PAGE}"], extract_tags(src))
        for page in wrapped.split("{PAGE}"):
            lines = page.split("\n")
            self.assertLessEqual(len(lines), 3)
            for line in lines:
                self.assertLessEqual(measure_line_px(line), 148)

        # With auto_paginate=False, no extra {PAGE} tags are added
        wrapped_no_page = wrap_dialogue_text(src, max_px=148, auto_paginate=False)
        self.assertEqual(extract_tags(wrapped_no_page), extract_tags(src))
        for line in wrapped_no_page.split("\n"):
            self.assertLessEqual(measure_line_px(line), 148)


class TestValidator(unittest.TestCase):
    """Test validator rules, error codes, and CLI exit status."""

    def _base_entry(self, **overrides):
        entry = {
            "id": "AREAD000.DAT:8:0:2",
            "file": "AREAD000.DAT",
            "entry_index": 8,
            "section": 0,
            "slice_index": 2,
            "slots": [2],
            "context": "dialogue_1p",
            "max_px": 148,
            "max_lines": 3,
            "preserve_line_count": False,
            "locked": False,
            "en": '{WIN:04}{PORTRAIT:C2:40}"I heard there was\nlots of people\nworking here,{PAGE}but I sure don\'t see\n\'em!"',
            "ptbr": '{WIN:04}{PORTRAIT:C2:40}"Ouvi dizer que\nhavia muita gente\ntrabalhando aqui,{PAGE}mas não vejo\nninguém!"',
        }
        entry.update(overrides)
        return entry

    def test_valid_ptbr_entry_passes(self):
        errs = validate_entry(self._base_entry())
        self.assertEqual(errs, [])

    def test_detects_corrupted_portrait_tag(self):
        entry = self._base_entry(
            ptbr='{WIN:04}{PORTRAIT:C2:65}"Ouvi dizer que\nhavia muita gente\ntrabalhando aqui,{PAGE}mas não vejo\nninguém!"'
        )
        errs = validate_entry(entry)
        self.assertTrue(any(e.code == "TAG_MISMATCH" for e in errs), errs)

    def test_detects_vwf_pixel_overflow(self):
        entry = self._base_entry(
            ptbr='{WIN:04}{PORTRAIT:C2:40}"Esta linha em português é absurdamente longa para a caixa com retrato!{PAGE}Ok!"'
        )
        errs = validate_entry(entry)
        self.assertTrue(any(e.code == "LINE_WIDTH_OVERFLOW" for e in errs), errs)

    def test_detects_page_line_overflow(self):
        entry = self._base_entry(
            ptbr='{WIN:04}{PORTRAIT:C2:40}"Linha 1\nLinha 2\nLinha 3\nLinha 4{PAGE}Ok!"'
        )
        errs = validate_entry(entry)
        self.assertTrue(any(e.code == "PAGE_LINES_OVERFLOW" for e in errs), errs)

    def test_detects_choice_line_count_mismatch(self):
        entry = self._base_entry(
            context="choice",
            max_px=140,
            max_lines=3,
            en="Save your game?{CHOICE:82:82}Yes\nNo",
            ptbr="Salvar o jogo?{CHOICE:82:82}Sim\nNão\nTalvez",
        )
        errs = validate_entry(entry)
        self.assertTrue(any(e.code == "CHOICE_COUNT_MISMATCH" for e in errs), errs)

    def test_choice_nl2_replaced_with_newline_rejected(self):
        # Replacing {NL2} (0x08 continuation wrap) with \n (0x01 option separator) injects a
        # bogus selectable choice option and MUST be rejected with CHOICE_COUNT_MISMATCH.
        entry = self._base_entry(
            context="choice",
            max_px=140,
            max_lines=None,
            en="Pick:{CHOICE:81:93}Finding enemies'{NL2}  weaknesses\nAbout treasure\nQuit",
            ptbr="Escolha:{CHOICE:81:93}Fraquezas dos\n  inimigos\nSobre tesouros\nSair",
        )
        errs = validate_entry(entry)
        self.assertTrue(any(e.code == "CHOICE_COUNT_MISMATCH" for e in errs), errs)

    def test_choice_nl2_valid_wrap_and_unwrap_accepted(self):
        # Unwrapping a 2-line {NL2} choice to 1 line or wrapping another option with {NL2}
        # preserves the exact selectable choice count (\n-separated) and MUST pass.
        en = "Pick:{CHOICE:81:93}Finding enemies'{NL2}  weaknesses\nAbout treasure\nQuit"
        unwrapped = self._base_entry(
            context="choice",
            max_px=140,
            max_lines=None,
            en=en,
            ptbr="Escolha:{CHOICE:81:93}Fraquezas inimigas\nSobre tesouros\nSair",
        )
        self.assertEqual(validate_entry(unwrapped), [])

        rewrapped = self._base_entry(
            context="choice",
            max_px=140,
            max_lines=None,
            en=en,
            ptbr="Escolha:{CHOICE:81:93}Fraquezas inimigas\nSobre baús e{NL2}  tesouros\nSair",
        )
        self.assertEqual(validate_entry(rewrapped), [])

    def test_detects_unmapped_char(self):
        entry = self._base_entry(
            ptbr='{WIN:04}{PORTRAIT:C2:40}"Olá — tudo bem?{PAGE}Sim!"'
        )
        errs = validate_entry(entry)
        self.assertTrue(any(e.code == "INVALID_ENCODING" for e in errs), errs)

    def test_detects_locked_entry_modified(self):
        entry = self._base_entry(
            locked=True,
            en="Healing Herb",
            ptbr="Erva Curativa",
        )
        errs = validate_entry(entry)
        self.assertTrue(any(e.code == "LOCKED_MODIFIED" for e in errs), errs)

    def test_allows_variable_reordering_in_ptbr(self):
        entry = self._base_entry(
            context="battle_sys",
            max_px=232,
            max_lines=2,
            en="{CHAR:00} used {COLOR:02}{CAT:04:EF}{/COLOR}!",
            ptbr="{COLOR:02}{CAT:04:EF}{/COLOR} foi usado por {CHAR:00}!",
        )
        self.assertEqual(validate_entry(entry), [])

    def test_cli_exit_codes(self):
        repo_root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as td:
            good_path = Path(td) / "good.json"
            bad_path = Path(td) / "bad.json"
            good_path.write_text(
                json.dumps({"shard_id": "test_good", "version": 2, "entries": [self._base_entry()]}),
                encoding="utf-8",
            )
            bad_path.write_text(
                json.dumps(
                    {
                        "shard_id": "test_bad",
                        "version": 2,
                        "entries": [self._base_entry(ptbr='{WIN:04}"sem retrato!{PAGE}ops"')],
                    }
                ),
                encoding="utf-8",
            )
            r_good = subprocess.run(
                [sys.executable, "-m", "bof4_ptbr.validate", str(good_path)],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(r_good.returncode, 0, r_good.stdout + r_good.stderr)
            self.assertNotIn("RuntimeWarning", r_good.stderr)

            r_bad = subprocess.run(
                [sys.executable, "-m", "bof4_ptbr.validate", str(bad_path)],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(r_bad.returncode, 0)


if __name__ == "__main__":
    unittest.main()
