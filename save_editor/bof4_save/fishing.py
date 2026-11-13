"""Fishing system manager for Breath of Fire IV."""

import struct
from typing import Dict, List, Any
from .constants import (
    FISH_LENGTHS_OFFSET,
    FISH_POINTS_OFFSET,
    FISHING_LURE_OFFSET,
    FISHING_ROD_OFFSET,
    FISHERMAN_RANK_OFFSET,
    FISH_SPECIES,
    FISHING_RODS,
    FISHING_LURES,
    FISHERMAN_RANKS,
)


class FishingManager:
    """Manages fishing records, rods, lures, and fisherman rank."""

    def __init__(self, data: bytearray):
        self.data = data

    @property
    def rod(self) -> int:
        return self.data[FISHING_ROD_OFFSET]

    @rod.setter
    def rod(self, val: int):
        self.data[FISHING_ROD_OFFSET] = max(0, min(len(FISHING_RODS) - 1, int(val)))

    @property
    def lure(self) -> int:
        return self.data[FISHING_LURE_OFFSET]

    @lure.setter
    def lure(self, val: int):
        self.data[FISHING_LURE_OFFSET] = int(val) & 0xFF

    @property
    def rank(self) -> int:
        return self.data[FISHERMAN_RANK_OFFSET]

    @rank.setter
    def rank(self, val: int):
        self.data[FISHERMAN_RANK_OFFSET] = max(0, min(len(FISHERMAN_RANKS) - 1, int(val)))

    def get_fish_length(self, index: int) -> int:
        if not (0 <= index < 30):
            raise IndexError("Fish index must be 0-29")
        return struct.unpack_from("<H", self.data, FISH_LENGTHS_OFFSET + index * 2)[0]

    def set_fish_length(self, index: int, length: int):
        if not (0 <= index < 30):
            raise IndexError("Fish index must be 0-29")
        struct.pack_into("<H", self.data, FISH_LENGTHS_OFFSET + index * 2, max(0, min(65535, int(length))))

    def get_fish_points(self, index: int) -> int:
        if not (0 <= index < 30):
            raise IndexError("Fish index must be 0-29")
        return struct.unpack_from("<H", self.data, FISH_POINTS_OFFSET + index * 2)[0]

    def set_fish_points(self, index: int, points: int):
        if not (0 <= index < 30):
            raise IndexError("Fish index must be 0-29")
        struct.pack_into("<H", self.data, FISH_POINTS_OFFSET + index * 2, max(0, min(65535, int(points))))

    @property
    def total_points(self) -> int:
        pts = struct.unpack_from("<30H", self.data, FISH_POINTS_OFFSET)
        return sum(pts)

    def get_all_records(self) -> List[Dict[str, Any]]:
        records = []
        for sp in FISH_SPECIES:
            idx = sp["id"]
            records.append({
                "id": idx,
                "item_id": sp["item_id"],
                "name": sp["name"],
                "name_pt": sp["name_pt"],
                "max_len": sp["max_len"],
                "max_pts": sp["max_pts"],
                "length": self.get_fish_length(idx),
                "points": self.get_fish_points(idx),
            })
        return records

    def max_all_fishing(self):
        """Sets all 30 fish species to max length & points, Master Rod, and rank 9 (The Fish)."""
        for sp in FISH_SPECIES:
            idx = sp["id"]
            self.set_fish_length(idx, sp["max_len"])
            self.set_fish_points(idx, sp["max_pts"])

        self.rod = 5  # Master's Rod
        self.lure = 0x02  # Platinum Top
        self.rank = 9  # The Fish
