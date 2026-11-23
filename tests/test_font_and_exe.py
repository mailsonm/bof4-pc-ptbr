"""Unit and integration tests for bof4_ptbr.font_builder and bof4_ptbr.exe_patcher.

All tests run strictly against temporary copies of clean INIT.DAT and BOF4.exe;
the clean game directory is read-only and verified unmodified.
"""

from __future__ import annotations

import hashlib
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

from bof4_ptbr import exe_patcher, font_builder

CLEAN_GAME_DIR = Path(
    "/home/mailson/Games/breath-of-fire-iv/drive_c/GOG Games/Breath of Fire IV"
)
CLEAN_INIT_PATH = CLEAN_GAME_DIR / "DAT" / "INIT.DAT"
CLEAN_EXE_PATH = CLEAN_GAME_DIR / "BOF4.exe"


class TestFontBuilder(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.init_bytes = CLEAN_INIT_PATH.read_bytes()
        cls.exe_bytes = CLEAN_EXE_PATH.read_bytes()

    def test_ptbr_char_contract(self) -> None:
        self.assertEqual(len(font_builder.PTBR_CHARS), 26)
        self.assertEqual(font_builder.CHAR_TO_BYTE["á"], 0x88)
        self.assertEqual(font_builder.CHAR_TO_BYTE["ç"], 0x93)
        self.assertEqual(font_builder.CHAR_TO_BYTE["Á"], 0x94)
        self.assertEqual(font_builder.CHAR_TO_BYTE["Õ"], 0x9D)
        self.assertEqual(font_builder.CHAR_TO_BYTE["Ç"], 0x9F)
        self.assertEqual(font_builder.CHAR_TO_BYTE["º"], 0xA0)
        self.assertEqual(font_builder.CHAR_TO_BYTE["ª"], 0xA1)

    def test_patch_init_fonts_sizes_and_vanilla_preservation(self) -> None:
        orig_f16, orig_f24 = font_builder.extract_init_fonts(self.init_bytes)
        self.assertEqual(len(orig_f16), 104 * 128)
        self.assertEqual(len(orig_f24), 104 * 288)

        patched_init = font_builder.patch_init_fonts(self.init_bytes)
        # Delta must equal exactly 26 * (128 + 288) = 10,816 bytes (0 padding)
        self.assertEqual(len(patched_init), len(self.init_bytes) + 26 * (128 + 288))

        new_f16, new_f24 = font_builder.extract_init_fonts(patched_init)
        self.assertEqual(len(new_f16), 130 * 128)
        self.assertEqual(len(new_f24), 130 * 288)

        # Vanilla glyphs 0x20..0x87 must be 100% untouched byte-for-byte
        self.assertEqual(new_f16[: len(orig_f16)], orig_f16)
        self.assertEqual(new_f24[: len(orig_f24)], orig_f24)

        # Verify all 12 INIT.DAT TOC entries remain 1-byte-packed with 0 gaps & 0 trailing pad
        first_off = struct.unpack_from("<I", patched_init, 0)[0]
        self.assertEqual(first_off, 12 * 16)
        expected_off = first_off
        for i in range(12):
            off, sz, type_param, dest = struct.unpack_from("<4I", patched_init, i * 16)
            self.assertEqual(off, expected_off)
            self.assertGreater(sz, 0)
            expected_off += sz
        self.assertEqual(expected_off, len(patched_init))

        # Verify every synthesized glyph has non-empty pixels and valid 0..8 nibbles
        for gid in range(104, 130):
            for dim, buf in ((16, new_f16), (24, new_f24)):
                grid = font_builder.decode_glyph_4bpp(buf, gid, dim)
                bb = font_builder.glyph_bbox(grid)
                self.assertIsNotNone(bb, f"Empty glyph {gid} ({dim}px)")
                for row in grid:
                    for nibble in row:
                        self.assertGreaterEqual(nibble, 0)
                        self.assertLessEqual(nibble, 8)

    def test_vwf_metrics_api(self) -> None:
        metrics = font_builder.get_ptbr_vwf_metrics()
        self.assertEqual(set(metrics.keys()), {"vwf_24", "vwf_16", "vwf_dlg"})
        self.assertEqual(metrics["vwf_24"], font_builder.PTBR_VWF_24)
        self.assertEqual(metrics["vwf_16"], font_builder.PTBR_VWF_16)
        self.assertEqual(metrics["vwf_dlg"], font_builder.PTBR_VWF_24)
        for code in range(0x88, 0xA2):
            lb24, adv24 = metrics["vwf_24"][code]
            lb16, adv16 = metrics["vwf_16"][code]
            self.assertTrue(0 <= lb24 <= 16 and 6 <= adv24 <= 24)
            self.assertTrue(0 <= lb16 <= 12 and 4 <= adv16 <= 16)

    def test_render_qa_pngs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = font_builder.render_qa_pngs(self.init_bytes, self.exe_bytes, td)
            for key in ("font_24", "font_16", "sample"):
                p = Path(out[key])
                self.assertTrue(p.is_file(), f"Missing PNG {p}")
                self.assertGreater(p.stat().st_size, 1000)
                # PNG magic header check
                self.assertEqual(p.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")


class TestExePatcher(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.clean_exe_bytes = CLEAN_EXE_PATH.read_bytes()

    def test_clean_exe_checksum_and_sha256(self) -> None:
        self.assertEqual(
            hashlib.sha256(self.clean_exe_bytes).hexdigest(),
            exe_patcher.CLEAN_BOF4_EXE_SHA256,
        )
        self.assertTrue(exe_patcher.verify_pe_checksum(self.clean_exe_bytes))

    def test_apply_verify_and_restore_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_exe = Path(td) / "BOF4.exe"
            shutil.copy2(CLEAN_EXE_PATH, tmp_exe)

            # Apply patch with backup
            res = exe_patcher.apply_exe_patch(tmp_exe, create_backup=True)
            self.assertTrue(res["pe_checksum_valid"])
            self.assertTrue(Path(res["backup_path"]).is_file())

            patched = tmp_exe.read_bytes()
            self.assertEqual(len(patched), len(self.clean_exe_bytes))
            self.assertNotEqual(res["patched_sha256"], exe_patcher.CLEAN_BOF4_EXE_SHA256)
            self.assertTrue(exe_patcher.verify_pe_checksum(patched))

            # Verify PE SecurityDir zeroed
            self.assertEqual(
                patched[exe_patcher.PE_SECURITY_DIR_OFFSET : exe_patcher.PE_SECURITY_DIR_OFFSET + 8],
                b"\x00" * 8,
            )

            # Verify Title Menu & HUD strings
            self.assertEqual(patched[0x3407AC : 0x3407AC + 12], b"NOVO JOGO\x00\x00\x00")
            self.assertEqual(patched[0x3407A0 : 0x3407A0 + 12], b"CARREGAR\x00\x00\x00\x00")
            # OPÇÕES: O(0x4F) P(0x50) Ç(0x9F) Õ(0x9D) E(0x45) S(0x53)
            self.assertEqual(patched[0x340798 : 0x340798 + 8], b"OP\x9f\x9dES\x00\x00")
            self.assertEqual(patched[0x2F918C : 0x2F918C + 8], b"MELHOR\x00\x00")

            # Verify NEW RECORD redirected to .rdata safe cave 0x008D3F34 (Raw 0x2BE134)
            self.assertEqual(patched[0x2BE134 : 0x2BE134 + 13], b"NOVO RECORDE\x00")
            for _, raw_off in exe_patcher.NEW_RECORD_XREFS:
                self.assertEqual(
                    struct.unpack_from("<I", patched, raw_off)[0],
                    exe_patcher.RDATA_CAVE_NEW_RECORD_VA,
                )

            # Verify Compass E/W -> L/O redirects AND original keyboard 'E'/'W' preserved!
            self.assertEqual(
                struct.unpack_from("<I", patched, exe_patcher.COMPASS_E_XREF_RAW)[0],
                exe_patcher.COMPASS_L_VA,
            )
            self.assertEqual(
                struct.unpack_from("<I", patched, exe_patcher.COMPASS_W_XREF_RAW)[0],
                exe_patcher.COMPASS_O_VA,
            )
            self.assertEqual(patched[0x2BEDDC : 0x2BEDDE], b"E\x00")
            self.assertEqual(patched[0x2BEDE0 : 0x2BEDE2], b"W\x00")

            # Verify VWF_dlg, VWF_24, and relocated VWF_16 in .text cave (0x006A7800)
            self.assertEqual(
                patched[0x2A79C0 : 0x2A7A00], b"\x00" * 64
            )  # zeroed -0x40 base
            self.assertEqual(
                patched[0x2A7A00 : 0x2A7A00 + 208],
                self.clean_exe_bytes[0x33CFE0 : 0x33CFE0 + 208],
            )
            for idx, code in enumerate(range(0x88, 0xA2)):
                lb24, adv24 = font_builder.PTBR_VWF_24[code]
                lb16, adv16 = font_builder.PTBR_VWF_16[code]
                self.assertEqual(
                    (patched[0x33704C + idx * 2], patched[0x33704C + idx * 2 + 1]),
                    (lb24, adv24),
                )
                self.assertEqual(
                    (patched[0x33D180 + idx * 2], patched[0x33D180 + idx * 2 + 1]),
                    (lb24, adv24),
                )
                self.assertEqual(
                    (patched[0x2A7A00 + 208 + idx * 2], patched[0x2A7A00 + 208 + idx * 2 + 1]),
                    (lb16, adv16),
                )
            for _, raw_off, _, new_va in exe_patcher.VWF_16_CODE_REFS:
                self.assertEqual(struct.unpack_from("<I", patched, raw_off)[0], new_va)

            # Verify live .data BSS tail (0x351C12..0x352200) is 100% UNTOUCHED!
            self.assertEqual(
                patched[0x351C12:0x352200],
                self.clean_exe_bytes[0x351C12:0x352200],
            )

            # Patching an already-patched EXE must fail cleanly (SHA256 guard)
            with self.assertRaises(exe_patcher.ExePatchError):
                exe_patcher.apply_exe_patch(tmp_exe, create_backup=True)

            # Restore from backup and verify exact SHA256 match
            rest = exe_patcher.restore_exe_backup(tmp_exe)
            self.assertTrue(rest["clean_match"])
            self.assertEqual(
                hashlib.sha256(tmp_exe.read_bytes()).hexdigest(),
                exe_patcher.CLEAN_BOF4_EXE_SHA256,
            )

    def test_build_exe_patch_spec_deterministic(self) -> None:
        spec = exe_patcher.build_exe_patch_spec(self.clean_exe_bytes)
        self.assertEqual(spec["clean_sha256"], exe_patcher.CLEAN_BOF4_EXE_SHA256)
        self.assertGreaterEqual(len(spec["ops"]), 18)

        # Applying spec ops manually must yield exact patched_sha256
        buf = bytearray(self.clean_exe_bytes)
        for op in spec["ops"]:
            off = op["offset"]
            exp = bytes.fromhex(op["expected_hex"])
            rep = bytes.fromhex(op["replacement_hex"])
            self.assertEqual(bytes(buf[off : off + len(exp)]), exp)
            buf[off : off + len(rep)] = rep
        self.assertEqual(hashlib.sha256(buf).hexdigest(), spec["patched_sha256"])
        self.assertTrue(exe_patcher.verify_pe_checksum(bytes(buf)))


if __name__ == "__main__":
    unittest.main()
