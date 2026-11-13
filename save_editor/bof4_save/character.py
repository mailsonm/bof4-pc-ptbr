"""Character model for Breath of Fire IV save file."""

import struct
from typing import Dict, Any
from .constants import (
    CHARACTERS_START,
    CHARACTER_BLOCK_SIZE,
    CHARACTER_NAMES,
    MAX_LEVEL,
    MAX_HP,
    MAX_AP,
    MAX_STAT,
)


class Character:
    """Represents a character entry within the save buffer."""

    def __init__(self, data: bytearray, index: int):
        if not (0 <= index < 7):
            raise ValueError(f"Invalid character index: {index}. Must be 0 to 6.")
        self.data = data
        self.index = index
        self.base_offset = CHARACTERS_START + index * CHARACTER_BLOCK_SIZE

    @property
    def default_info(self) -> Dict[str, Any]:
        return CHARACTER_NAMES[self.index]

    @property
    def name(self) -> str:
        raw = self.data[self.base_offset : self.base_offset + 6]
        return raw.decode("ascii", errors="ignore").rstrip("\x00")

    @name.setter
    def name(self, val: str):
        encoded = val.encode("ascii", errors="ignore")[:6]
        padded = encoded.ljust(6, b"\x00")
        self.data[self.base_offset : self.base_offset + 6] = padded

    @property
    def level(self) -> int:
        return self.data[self.base_offset + 0x0A]

    @level.setter
    def level(self, val: int):
        self.data[self.base_offset + 0x0A] = max(1, min(MAX_LEVEL, int(val)))

    @property
    def exp(self) -> int:
        return struct.unpack_from("<I", self.data, self.base_offset + 0x0C)[0]

    @exp.setter
    def exp(self, val: int):
        struct.pack_into("<I", self.data, self.base_offset + 0x0C, max(0, min(99_999_999, int(val))))

    @property
    def current_hp(self) -> int:
        return struct.unpack_from("<I", self.data, self.base_offset + 0x14)[0]

    @current_hp.setter
    def current_hp(self, val: int):
        struct.pack_into("<I", self.data, self.base_offset + 0x14, max(1, min(MAX_HP, int(val))))

    @property
    def current_ap(self) -> int:
        return struct.unpack_from("<I", self.data, self.base_offset + 0x18)[0]

    @current_ap.setter
    def current_ap(self, val: int):
        struct.pack_into("<I", self.data, self.base_offset + 0x18, max(0, min(MAX_AP, int(val))))

    @property
    def base_max_hp(self) -> int:
        return struct.unpack_from("<I", self.data, self.base_offset + 0x38)[0]

    @base_max_hp.setter
    def base_max_hp(self, val: int):
        struct.pack_into("<I", self.data, self.base_offset + 0x38, max(1, min(MAX_HP, int(val))))

    @property
    def base_max_ap(self) -> int:
        return struct.unpack_from("<I", self.data, self.base_offset + 0x3C)[0]

    @base_max_ap.setter
    def base_max_ap(self, val: int):
        struct.pack_into("<I", self.data, self.base_offset + 0x3C, max(0, min(MAX_AP, int(val))))

    @property
    def total_max_hp(self) -> int:
        return struct.unpack_from("<I", self.data, self.base_offset + 0x5C)[0]

    @total_max_hp.setter
    def total_max_hp(self, val: int):
        struct.pack_into("<I", self.data, self.base_offset + 0x5C, max(1, min(MAX_HP, int(val))))

    @property
    def total_max_ap(self) -> int:
        return struct.unpack_from("<I", self.data, self.base_offset + 0x60)[0]

    @total_max_ap.setter
    def total_max_ap(self, val: int):
        struct.pack_into("<I", self.data, self.base_offset + 0x60, max(0, min(MAX_AP, int(val))))

    @property
    def cp(self) -> int:
        return struct.unpack_from("<H", self.data, self.base_offset + 0x64)[0]

    @cp.setter
    def cp(self, val: int):
        struct.pack_into("<H", self.data, self.base_offset + 0x64, max(0, min(MAX_STAT, int(val))))

    @property
    def pwr(self) -> int:
        return struct.unpack_from("<H", self.data, self.base_offset + 0x66)[0]

    @pwr.setter
    def pwr(self, val: int):
        struct.pack_into("<H", self.data, self.base_offset + 0x66, max(0, min(MAX_STAT, int(val))))

    @property
    def defense(self) -> int:
        return struct.unpack_from("<H", self.data, self.base_offset + 0x68)[0]

    @defense.setter
    def defense(self, val: int):
        struct.pack_into("<H", self.data, self.base_offset + 0x68, max(0, min(MAX_STAT, int(val))))

    @property
    def agl(self) -> int:
        return struct.unpack_from("<H", self.data, self.base_offset + 0x6A)[0]

    @agl.setter
    def agl(self, val: int):
        struct.pack_into("<H", self.data, self.base_offset + 0x6A, max(0, min(MAX_STAT, int(val))))

    @property
    def wis(self) -> int:
        return struct.unpack_from("<H", self.data, self.base_offset + 0x6C)[0]

    @wis.setter
    def wis(self, val: int):
        struct.pack_into("<H", self.data, self.base_offset + 0x6C, max(0, min(MAX_STAT, int(val))))

    @property
    def master(self) -> int:
        return self.data[self.base_offset + 0x84]

    @master.setter
    def master(self, val: int):
        self.data[self.base_offset + 0x84] = max(0, min(255, int(val)))

    @property
    def weapon(self) -> int:
        return self.data[self.base_offset + 0x80]

    @weapon.setter
    def weapon(self, val: int):
        self.data[self.base_offset + 0x80] = max(0, min(255, int(val)))

    @property
    def armor(self) -> int:
        return self.data[self.base_offset + 0x81]

    @armor.setter
    def armor(self, val: int):
        self.data[self.base_offset + 0x81] = max(0, min(255, int(val)))

    @property
    def accessory(self) -> int:
        return self.data[self.base_offset + 0x82]

    @accessory.setter
    def accessory(self, val: int):
        self.data[self.base_offset + 0x82] = max(0, min(255, int(val)))

    def max_stats(self):
        """Maximizes character level, HP, AP, and all combat stats to caps."""
        self.level = MAX_LEVEL
        self.exp = 99_999_999
        self.current_hp = MAX_HP
        self.base_max_hp = MAX_HP
        self.total_max_hp = MAX_HP
        self.current_ap = MAX_AP
        self.base_max_ap = MAX_AP
        self.total_max_ap = MAX_AP
        self.cp = MAX_STAT
        self.pwr = MAX_STAT
        self.defense = MAX_STAT
        self.agl = MAX_STAT
        self.wis = MAX_STAT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "level": self.level,
            "exp": self.exp,
            "current_hp": self.current_hp,
            "total_max_hp": self.total_max_hp,
            "base_max_hp": self.base_max_hp,
            "current_ap": self.current_ap,
            "total_max_ap": self.total_max_ap,
            "base_max_ap": self.base_max_ap,
            "cp": self.cp,
            "pwr": self.pwr,
            "defense": self.defense,
            "agl": self.agl,
            "wis": self.wis,
            "master": self.master,
            "weapon": self.weapon,
            "armor": self.armor,
            "accessory": self.accessory,
        }
