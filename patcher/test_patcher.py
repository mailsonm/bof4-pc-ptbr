#!/usr/bin/env python3
"""Unit & temp-dir canary tests for Breath of Fire IV PT-BR v2.0.0 standalone patcher."""

import hashlib
import importlib.util
import os
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

PATCHER_DIR = Path(__file__).resolve().parent
try:
    from patcher import BoF4Patcher, VERSION, _verify_pe_checksum
except ImportError:
    _spec = importlib.util.spec_from_file_location("patcher_mod", PATCHER_DIR / "patcher.py")
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    BoF4Patcher = _mod.BoF4Patcher
    VERSION = _mod.VERSION
    _verify_pe_checksum = _mod._verify_pe_checksum

PKG_V2_PATH = PATCHER_DIR / "translation_v2.pkg"
CLEAN_GAME_DIR = Path(
    "/home/mailson/Games/breath-of-fire-iv/drive_c/GOG Games/Breath of Fire IV"
)


class TestBoF4Patcher(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.dat_dir = os.path.join(self.test_dir, "DAT")
        os.makedirs(self.dat_dir, exist_ok=True)

        with open(os.path.join(self.test_dir, "BOF4.exe"), "wb") as f:
            f.write(b"MZ_DUMMY_EXE")
        with open(os.path.join(self.dat_dir, "INIT.DAT"), "wb") as f:
            f.write(b"INIT_DUMMY")

<<<<<<< HEAD
        self.pkg_path = os.path.join(PATCHER_DIR, "translation_data.pkg")
        self.patcher = BoF4Patcher(self.test_dir, pkg_path=self.pkg_path)
=======
        self.patcher = BoF4Patcher(self.test_dir, pkg_path=str(PKG_V2_PATH))
>>>>>>> 3325f2c (feat: native PC PT-BR v2.0.0 translation, extended fonts, VWF & patcher)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_version_and_package_loading(self):
        self.assertEqual(VERSION, "2.0.0")
        meta = self.patcher.load_package()
        self.assertEqual(meta["format"], "bof4_ptbr_v2")
        self.assertEqual(meta["version"], "2.0.0")
        self.assertIn("INIT.DAT", meta["dat_patches"])
        self.assertEqual(len(meta["dat_patches"]), 305)
        self.assertEqual(meta["stats"]["dat_entries"], 319)
        self.assertEqual(meta["stats"]["exe_ops"], 21)

    def test_validate_game_dir(self):
        valid, _msg = self.patcher.validate_game_dir()
        self.assertTrue(valid)

    def test_validate_invalid_dir(self):
        invalid_patcher = BoF4Patcher("/tmp/non_existent_bof4_dir", pkg_path=str(PKG_V2_PATH))
        valid, _msg = invalid_patcher.validate_game_dir()
        self.assertFalse(valid)

    def test_backup_and_restore_dummy_cycle(self):
        self.assertFalse(self.patcher.has_backup())
        self.patcher.create_backup()
        self.assertTrue(self.patcher.has_backup())
        self.assertTrue(os.path.isfile(os.path.join(self.test_dir, "BOF4.exe.bak")))

        restored, errors = self.patcher.restore_backup()
        self.assertEqual(errors, [])
        self.assertGreaterEqual(restored, 2)
        self.assertFalse(self.patcher.is_patched())

    def test_full_canary_apply_verify_and_restore_on_clean_copy(self):
        """Full temp-dir canary against real clean DATs & BOF4.exe: apply, verify, restore."""
        if not (CLEAN_GAME_DIR / "BOF4.exe").is_file():
            self.skipTest("Clean game directory not available in environment")

        meta = self.patcher.load_package()
        target_dats = sorted(meta["dat_patches"].keys())

        with tempfile.TemporaryDirectory() as tmp_game:
            tmp_dat = Path(tmp_game) / "DAT"
            tmp_dat.mkdir(parents=True)
            shutil.copy2(CLEAN_GAME_DIR / "BOF4.exe", Path(tmp_game) / "BOF4.exe")

            orig_hashes = {
                "BOF4.exe": hashlib.sha256((CLEAN_GAME_DIR / "BOF4.exe").read_bytes()).hexdigest()
            }
            for fname in target_dats:
                src = CLEAN_GAME_DIR / "DAT" / fname
                shutil.copy2(src, tmp_dat / fname)
                orig_hashes[fname] = hashlib.sha256(src.read_bytes()).hexdigest()

            # Read clean INIT.DAT[7] (catalog) to assert untouched after patching
            clean_init = (CLEAN_GAME_DIR / "DAT" / "INIT.DAT").read_bytes()
            off7, sz7, _, _ = struct.unpack_from("<4I", clean_init, 7 * 16)
            clean_cat = clean_init[off7 : off7 + sz7]

            canary = BoF4Patcher(tmp_game, pkg_path=str(PKG_V2_PATH))
            patched_count, errors = canary.apply_patch()
            self.assertEqual(errors, [])
            self.assertEqual(patched_count, len(target_dats) + 1)  # 305 DATs + BOF4.exe
            self.assertTrue(canary.is_patched())
            self.assertTrue(canary.has_backup())

            # Verify BOF4.exe checksum & SHA256
            patched_exe = (Path(tmp_game) / "BOF4.exe").read_bytes()
            self.assertTrue(_verify_pe_checksum(patched_exe))
            self.assertEqual(
                hashlib.sha256(patched_exe).hexdigest(),
                meta["exe_patch_spec"]["patched_sha256"],
            )

            # Verify INIT.DAT[7] untouched & INIT.DAT[8..9] extended to 130 glyphs
            patched_init = (tmp_dat / "INIT.DAT").read_bytes()
            p_off7, p_sz7, _, _ = struct.unpack_from("<4I", patched_init, 7 * 16)
            self.assertEqual(patched_init[p_off7 : p_off7 + p_sz7], clean_cat)
            _, sz8, tp8, dest8 = struct.unpack_from("<4I", patched_init, 8 * 16)
            _, sz9, tp9, dest9 = struct.unpack_from("<4I", patched_init, 9 * 16)
            self.assertEqual((tp8, dest8, sz8), (5, 0x1000, 130 * 128))
            self.assertEqual((tp9, dest9, sz9), (5, 0x1801, 130 * 288))

            # Verify every patched DAT has 0 gaps, 0 trailing pad, and respects RAM ceilings
            ceilings = {0x0: 0x10000, 0x10000: 0x10000, 0x20000: 0x07000, 0x27000: 0x01000}
            for fname in target_dats:
                raw = (tmp_dat / fname).read_bytes()
                n = struct.unpack_from("<I", raw, 0)[0] // 16
                cur = n * 16
                for i in range(n):
                    off, sz, tp, dest = struct.unpack_from("<4I", raw, i * 16)
                    self.assertEqual(off, cur, f"Gap in {fname}[{i}]")
                    cur += sz
                    if tp == 0 and dest in ceilings:
                        self.assertLessEqual(sz, ceilings[dest], f"RAM ceiling exceeded in {fname}")
                self.assertEqual(cur, len(raw), f"Trailing pad in {fname}")

            # Restore and verify 100% SHA256 match on all 305 DATs + BOF4.exe
            restored_count, r_errors = canary.restore_backup()
            self.assertEqual(r_errors, [])
            self.assertEqual(restored_count, len(target_dats) + 1)
            self.assertFalse(canary.is_patched())
            self.assertEqual(
                hashlib.sha256((Path(tmp_game) / "BOF4.exe").read_bytes()).hexdigest(),
                orig_hashes["BOF4.exe"],
            )
            for fname in target_dats:
                self.assertEqual(
                    hashlib.sha256((tmp_dat / fname).read_bytes()).hexdigest(),
                    orig_hashes[fname],
                    f"Restore SHA256 mismatch for {fname}",
                )


if __name__ == "__main__":
    unittest.main()
