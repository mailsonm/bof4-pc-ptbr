#!/usr/bin/env python3
"""Unit tests for Breath of Fire IV translation patcher."""

import os
import shutil
import tempfile
import unittest
from patcher import BoF4Patcher


class TestBoF4Patcher(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.dat_dir = os.path.join(self.test_dir, "DAT")
        os.makedirs(self.dat_dir, exist_ok=True)

        # Create dummy BOF4.exe and INIT.DAT
        with open(os.path.join(self.test_dir, "BOF4.exe"), "wb") as f:
            f.write(b"MZ_DUMMY_EXE")
        with open(os.path.join(self.dat_dir, "INIT.DAT"), "wb") as f:
            f.write(b"INIT_DUMMY")

        self.pkg_path = "/home/mailson/.gemini/antigravity/scratch/bof4-nexus-mod/translation_data.pkg"
        self.patcher = BoF4Patcher(self.test_dir, pkg_path=self.pkg_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_validate_game_dir(self):
        valid, msg = self.patcher.validate_game_dir()
        self.assertTrue(valid)

    def test_validate_invalid_dir(self):
        invalid_patcher = BoF4Patcher("/tmp/non_existent_bof4_dir")
        valid, msg = invalid_patcher.validate_game_dir()
        self.assertFalse(valid)

    def test_package_loading(self):
        pkg = self.patcher.load_package()
        self.assertIn("INIT.DAT", pkg)
        self.assertGreater(len(pkg), 300)

    def test_backup_and_restore_cycle(self):
        self.assertFalse(self.patcher.has_backup())
        backed_up = self.patcher.create_backup()
        self.assertTrue(self.patcher.has_backup())

        # Test restore
        restored, errors = self.patcher.restore_backup()
        self.assertIn("INIT.DAT", os.listdir(self.dat_dir))
        self.assertFalse(self.patcher.is_patched())


if __name__ == "__main__":
    unittest.main()
