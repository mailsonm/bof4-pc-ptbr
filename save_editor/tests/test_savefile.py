"""Unit tests for Breath of Fire IV Save Editor."""

import os
import shutil
import tempfile
import unittest

from bof4_save import SaveFile, MAX_ZENNY, MAX_GP, MAX_LEVEL, MAX_HP, MAX_AP, MAX_STAT

REAL_SAVE_PATH = "/home/mailson/Games/breath-of-fire-iv/drive_c/GOG Games/Breath of Fire IV/SAV/01.DAT"


class TestBoF4SaveFile(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_save = os.path.join(self.temp_dir, "01.DAT")
        shutil.copy2(REAL_SAVE_PATH, self.temp_save)
        self.save = SaveFile(self.temp_save)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_checksum_valid_on_real_save(self):
        """Checks that the real save file passes XOR checksum validation."""
        self.assertTrue(self.save.is_checksum_valid())
        self.assertEqual(self.save.stored_checksum, self.save.calculate_checksum())

    def test_checksum_recalculation(self):
        """Verifies that altering data invalidates checksum until update_checksum is called."""
        self.save.zenny = 5000
        # The stored checksum has not been updated yet
        self.assertFalse(self.save.is_checksum_valid())
        self.save.update_checksum()
        self.assertTrue(self.save.is_checksum_valid())

    def test_zenny_manipulation(self):
        """Tests reading and modifying Zenny."""
        self.assertEqual(self.save.zenny, 335)
        self.save.zenny = 1234567
        self.assertEqual(self.save.zenny, 1234567)
        # Test max clamping
        self.save.zenny = 999_999_999
        self.assertEqual(self.save.zenny, MAX_ZENNY)

    def test_game_points_manipulation(self):
        """Tests reading and modifying Game Points (GP)."""
        self.assertEqual(self.save.gp, 1971)
        self.save.gp = 65000
        self.assertEqual(self.save.gp, 65000)
        # Test clamping
        self.save.gp = 200_000
        self.assertEqual(self.save.gp, MAX_GP)

    def test_character_data(self):
        """Tests reading and modifying character attributes."""
        ryu = self.save.get_character(0)
        self.assertEqual(ryu.name, "Ryu")
        self.assertEqual(ryu.level, 5)
        self.assertEqual(ryu.exp, 135)
        self.assertEqual(ryu.current_hp, 189)
        self.assertEqual(ryu.total_max_hp, 346)

        # Maximize Ryu
        ryu.max_stats()
        self.assertEqual(ryu.level, MAX_LEVEL)
        self.assertEqual(ryu.current_hp, MAX_HP)
        self.assertEqual(ryu.total_max_hp, MAX_HP)
        self.assertEqual(ryu.current_ap, MAX_AP)
        self.assertEqual(ryu.total_max_ap, MAX_AP)
        self.assertEqual(ryu.pwr, MAX_STAT)
        self.assertEqual(ryu.defense, MAX_STAT)
        self.assertEqual(ryu.agl, MAX_STAT)
        self.assertEqual(ryu.wis, MAX_STAT)

    def test_fishing_system(self):
        """Tests reading and maxing fishing records."""
        fishing = self.save.fishing
        # Fish 0 is Jellyfish
        self.assertEqual(fishing.get_fish_length(0), 29)
        self.assertEqual(fishing.get_fish_points(0), 72)
        initial_points = fishing.total_points
        self.assertEqual(initial_points, 332)

        # Maximize fishing
        fishing.max_all_fishing()
        self.assertEqual(fishing.rod, 5)  # Master's Rod
        self.assertEqual(fishing.lure, 2)  # Platinum Top
        self.assertEqual(fishing.rank, 9)  # The Fish
        self.assertGreater(fishing.total_points, 9000)

    def test_inventory_operations(self):
        """Tests inventory slots and bulk quantity modification."""
        inv = self.save.inventory
        # Check slot 0 (Healing Herb)
        iid, qty = inv.get_slot(0, 0)
        self.assertEqual(iid, 1)
        self.assertEqual(qty, 5)

        # Modify slot
        inv.set_slot(0, 0, 1, 99)
        self.assertEqual(inv.get_slot(0, 0), (1, 99))

        # Max existing
        inv.set_all_existing_to_max(99)
        iid2, qty2 = inv.get_slot(0, 1)  # Slot 1 is Vitamin (35)
        self.assertEqual(qty2, 99)

    def test_god_mode(self):
        """Tests complete God Mode application."""
        self.save.apply_god_mode()
        self.assertEqual(self.save.zenny, MAX_ZENNY)
        self.assertEqual(self.save.gp, 65000)
        self.assertEqual(self.save.fishing.rank, 9)
        self.assertEqual(self.save.get_character(0).level, 99)
        self.assertEqual(self.save.get_character(6).level, 99)  # Fou-Lu

    def test_save_and_backup(self):
        """Tests save file persistence and backup creation."""
        self.save.zenny = 999999
        self.save.save(make_backup=True)

        # Verify file on disk
        reloaded = SaveFile(self.temp_save)
        self.assertEqual(reloaded.zenny, 999999)
        self.assertTrue(reloaded.is_checksum_valid())

        # Verify backup exists
        backups = [f for f in os.listdir(self.temp_dir) if f.endswith(".bak")]
        self.assertEqual(len(backups), 1)


if __name__ == "__main__":
    unittest.main()
