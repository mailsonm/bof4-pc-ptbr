"""Main SaveFile model for Breath of Fire IV."""

import os
import shutil
import struct
from datetime import datetime
from typing import Optional, List

from .constants import (
    EXPECTED_SAVE_SIZE,
    CHECKSUM_RANGE_END,
    CHECKSUM_OFFSET,
    ZENNY_OFFSET,
    GP_OFFSET,
    MAX_ZENNY,
    MAX_GP,
    CHARACTER_COUNT,
)
from .character import Character
from .fishing import FishingManager
from .inventory import Inventory


class SaveFile:
    """Manages reading, parsing, modifying, and saving Breath of Fire IV save files."""

    def __init__(self, file_path: Optional[str] = None, data: Optional[bytearray] = None):
        self.file_path = file_path
        if data is not None:
            self.data = bytearray(data)
        elif file_path is not None:
            with open(file_path, "rb") as f:
                self.data = bytearray(f.read())
        else:
            raise ValueError("Either file_path or data must be provided")

        if len(self.data) < EXPECTED_SAVE_SIZE:
            raise ValueError(
                f"File size {len(self.data)} bytes is smaller than expected {EXPECTED_SAVE_SIZE} bytes."
            )

        # Initialize sub-managers
        self.characters: List[Character] = [
            Character(self.data, i) for i in range(CHARACTER_COUNT)
        ]
        self.fishing = FishingManager(self.data)
        self.inventory = Inventory(self.data)

    # Checksum handling
    def calculate_checksum(self) -> int:
        """Calculates 8-bit XOR checksum over bytes 0x0000 to 0x184E."""
        checksum = 0
        for b in self.data[:CHECKSUM_RANGE_END]:
            checksum ^= b
        return checksum

    @property
    def stored_checksum(self) -> int:
        return self.data[CHECKSUM_OFFSET]

    def is_checksum_valid(self) -> bool:
        return self.stored_checksum == self.calculate_checksum()

    def update_checksum(self):
        """Recalculates and updates the checksum byte at 0x184F."""
        self.data[CHECKSUM_OFFSET] = self.calculate_checksum()

    # Economy & Points
    @property
    def zenny(self) -> int:
        return struct.unpack_from("<I", self.data, ZENNY_OFFSET)[0]

    @zenny.setter
    def zenny(self, value: int):
        struct.pack_into("<I", self.data, ZENNY_OFFSET, max(0, min(MAX_ZENNY, int(value))))

    @property
    def gp(self) -> int:
        """Game Points (GP) used to unlock dragon breath / transformations."""
        return struct.unpack_from("<I", self.data, GP_OFFSET)[0]

    @gp.setter
    def gp(self, value: int):
        struct.pack_into("<I", self.data, GP_OFFSET, max(0, min(MAX_GP, int(value))))

    def get_character(self, index: int) -> Character:
        if not (0 <= index < len(self.characters)):
            raise IndexError(f"Character index out of range: {index}")
        return self.characters[index]

    def apply_god_mode(self, max_items_catalog: bool = False):
        """Applies ultimate enhancements to the save file.

        - Max Zenny (99,999,999)
        - Max Game Points (65,000 for dragon transformations)
        - Max Fishing Book records, Master's Rod, and 'The Fish' rank
        - Max stats and levels for all 7 party members
        - Max quantities for items
        """
        self.zenny = MAX_ZENNY
        self.gp = 65_000
        self.fishing.max_all_fishing()

        for char in self.characters:
            char.max_stats()

        if max_items_catalog:
            self.inventory.max_all_catalog()
        else:
            self.inventory.set_all_existing_to_max()

    def create_backup(self, backup_dir: Optional[str] = None) -> Optional[str]:
        """Creates a timestamped backup of the current save file."""
        if not self.file_path or not os.path.exists(self.file_path):
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.basename(self.file_path)
        backup_name = f"{base_name}.{timestamp}.bak"

        if backup_dir:
            os.makedirs(backup_dir, exist_ok=True)
            backup_path = os.path.join(backup_dir, backup_name)
        else:
            backup_path = os.path.join(os.path.dirname(self.file_path), backup_name)

        shutil.copy2(self.file_path, backup_path)
        return backup_path

    def save(self, output_path: Optional[str] = None, make_backup: bool = True) -> str:
        """Updates checksum and writes data to file."""
        target_path = output_path or self.file_path
        if not target_path:
            raise ValueError("No output path specified for saving.")

        if make_backup and os.path.exists(target_path):
            self.create_backup()

        self.update_checksum()

        temp_path = f"{target_path}.tmp"
        with open(temp_path, "wb") as f:
            f.write(self.data)

        os.replace(temp_path, target_path)
        self.file_path = target_path
        return target_path
