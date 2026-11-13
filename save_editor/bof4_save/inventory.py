"""Inventory manager for Breath of Fire IV."""

from typing import List, Dict, Tuple, Any
from .constants import (
    INVENTORY_START,
    INVENTORY_CATEGORY_SIZE,
    MAX_ITEM_QTY,
)
from .items_data import ITEM_CATEGORIES, get_item_name


class Inventory:
    """Manages 4 categories of inventory items (Items, Weapons, Armor, Accessories)."""

    def __init__(self, data: bytearray):
        self.data = data

    def _get_slot_offset(self, category_idx: int, slot_idx: int) -> int:
        if not (0 <= category_idx < 4):
            raise IndexError("Category must be 0 (Items), 1 (Weapons), 2 (Armor), or 3 (Accessories)")
        if not (0 <= slot_idx < 128):
            raise IndexError("Slot index must be 0-127")
        return INVENTORY_START + category_idx * INVENTORY_CATEGORY_SIZE + slot_idx * 2

    def get_slot(self, category_idx: int, slot_idx: int) -> Tuple[int, int]:
        offset = self._get_slot_offset(category_idx, slot_idx)
        return self.data[offset], self.data[offset + 1]

    def set_slot(self, category_idx: int, slot_idx: int, item_id: int, qty: int):
        offset = self._get_slot_offset(category_idx, slot_idx)
        item_id = max(0, min(255, int(item_id)))
        qty = max(0, min(MAX_ITEM_QTY, int(qty)))
        if item_id == 0:
            qty = 0
        self.data[offset] = item_id
        self.data[offset + 1] = qty

    def clear_slot(self, category_idx: int, slot_idx: int):
        self.set_slot(category_idx, slot_idx, 0, 0)

    def get_category_slots(self, category_idx: int) -> List[Dict[str, Any]]:
        slots = []
        for slot in range(128):
            iid, qty = self.get_slot(category_idx, slot)
            slots.append({
                "slot": slot,
                "item_id": iid,
                "name": get_item_name(category_idx, iid),
                "qty": qty,
                "is_empty": (iid == 0 or qty == 0),
            })
        return slots

    def set_all_existing_to_max(self, qty: int = MAX_ITEM_QTY):
        """Sets the quantity of all non-empty items across all categories to max (99)."""
        for cat in range(4):
            for slot in range(128):
                iid, curr_qty = self.get_slot(cat, slot)
                if iid != 0 and curr_qty > 0:
                    self.set_slot(cat, slot, iid, qty)

    def fill_all_category_items(self, category_idx: int, qty: int = MAX_ITEM_QTY):
        """Fills the category with all items from its catalog up to 128 slots."""
        cat_info = ITEM_CATEGORIES.get(category_idx)
        if not cat_info:
            return
        table = cat_info["table"]
        # Skip index 0 ('Nothing')
        slot = 0
        for iid in range(1, len(table)):
            if slot >= 128:
                break
            self.set_slot(category_idx, slot, iid, qty)
            slot += 1

    def max_all_catalog(self, qty: int = MAX_ITEM_QTY):
        """Fills all 4 inventory categories with all items from their catalogs with max quantity."""
        for cat in range(4):
            self.fill_all_category_items(cat, qty)
