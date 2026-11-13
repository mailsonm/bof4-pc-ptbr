"""Constants, offsets, and data dictionaries for Breath of Fire IV Save Editor.

Supports GOG, Steam, and PC editions of Breath of Fire IV.
"""

from typing import Dict, List

DEFAULT_SAVE_DIR = "/home/mailson/Games/breath-of-fire-iv/drive_c/GOG Games/Breath of Fire IV/SAV"
EXPECTED_SAVE_SIZE = 6272  # 0x1880
CHECKSUM_RANGE_END = 0x184F  # XOR bytes 0x0000 to 0x184E
CHECKSUM_OFFSET = 0x184F     # Stored XOR checksum byte

# Economy & Progression Offsets
ZENNY_OFFSET = 0x05B4  # 4 bytes unsigned int (little-endian)
GP_OFFSET = 0x0F98     # 4 bytes unsigned int (Game Points for Dragon Evolutions)

# Fishing Offsets
FISH_LENGTHS_OFFSET = 0x1154  # 30 * uint16 (max length in cm for each fish species)
FISH_POINTS_OFFSET = 0x1190   # 30 * uint16 (points earned for each fish species)
FISHING_LURE_OFFSET = 0x11CC  # uint8 (current equipped lure)
FISHING_ROD_OFFSET = 0x11CD   # uint8 (current equipped rod)
FISHERMAN_RANK_OFFSET = 0x11CE  # uint8 (0 to 9)

# Character Data Offsets
CHARACTERS_START = 0x0180
CHARACTER_BLOCK_SIZE = 0x98  # 152 bytes per character
CHARACTER_COUNT = 7

# Inventory Offsets
INVENTORY_START = 0x05CC
INVENTORY_CATEGORY_SIZE = 512  # 128 slots * 2 bytes (ID, Qty)
INVENTORY_CATEGORIES = ["Item", "Weapon", "Armor", "Accessory"]

# Limits
MAX_ZENNY = 99_999_999
MAX_GP = 99_999  # Dragon transformation thresholds: 10k, 25k, 35k, 50k, 62k
MAX_FISHING_POINTS = 9999
MAX_LEVEL = 99
MAX_HP = 9999
MAX_AP = 999
MAX_STAT = 999
MAX_ITEM_QTY = 99

# Characters
CHARACTER_NAMES = [
    {"id": 0, "default_name": "Ryu", "title": "O Dragão do Destino"},
    {"id": 1, "default_name": "Nina", "title": "Princesa de Wyndia"},
    {"id": 2, "default_name": "Cray", "title": "Líder dos Woren"},
    {"id": 3, "default_name": "Scias", "title": "Espadachim Mercenário"},
    {"id": 4, "default_name": "Ursula", "title": "Capitã do Império Fou"},
    {"id": 5, "default_name": "Ershin", "title": "Armadura Misteriosa"},
    {"id": 6, "default_name": "Fou-Lu", "title": "O Primeiro Imperador"},
]

# 30 Fish Species in the Fish Book
FISH_SPECIES: List[Dict[str, any]] = [
    {"id": 0, "item_id": 45, "name": "Jellyfish", "name_pt": "Água-Viva", "max_len": 30, "max_pts": 80},
    {"id": 1, "item_id": 46, "name": "Piranha", "name_pt": "Piranha", "max_len": 40, "max_pts": 150},
    {"id": 2, "item_id": 47, "name": "Bass", "name_pt": "Robalo", "max_len": 60, "max_pts": 200},
    {"id": 3, "item_id": 48, "name": "Blue Gill", "name_pt": "Bluegill", "max_len": 50, "max_pts": 250},
    {"id": 4, "item_id": 49, "name": "Sweetfish", "name_pt": "Ayu / Sweetfish", "max_len": 25, "max_pts": 150},
    {"id": 5, "item_id": 50, "name": "Browntail", "name_pt": "Truta Marrom", "max_len": 70, "max_pts": 250},
    {"id": 6, "item_id": 51, "name": "Black Bass", "name_pt": "Black Bass", "max_len": 70, "max_pts": 300},
    {"id": 7, "item_id": 52, "name": "Angelfish", "name_pt": "Acará-Bandeira", "max_len": 30, "max_pts": 250},
    {"id": 8, "item_id": 53, "name": "Trout", "name_pt": "Truta", "max_len": 40, "max_pts": 200},
    {"id": 9, "item_id": 54, "name": "Rainbow Trout", "name_pt": "Truta Arco-Íris", "max_len": 70, "max_pts": 350},
    {"id": 10, "item_id": 55, "name": "Bullcat", "name_pt": "Peixe-Gato / Bullcat", "max_len": 80, "max_pts": 380},
    {"id": 11, "item_id": 56, "name": "Martian Squid", "name_pt": "Lula Marciana", "max_len": 70, "max_pts": 350},
    {"id": 12, "item_id": 57, "name": "Dorado", "name_pt": "Dourado", "max_len": 90, "max_pts": 400},
    {"id": 13, "item_id": 58, "name": "Salmon", "name_pt": "Salmão", "max_len": 140, "max_pts": 400},
    {"id": 14, "item_id": 59, "name": "Barandy", "name_pt": "Barandy", "max_len": 200, "max_pts": 700},
    {"id": 15, "item_id": 60, "name": "Sturgeon", "name_pt": "Esturjão", "max_len": 220, "max_pts": 700},
    {"id": 16, "item_id": 61, "name": "Man-o'-War", "name_pt": "Caravela-Portuguesa", "max_len": 30, "max_pts": 80},
    {"id": 17, "item_id": 62, "name": "Flying Fish", "name_pt": "Peixe-Voador", "max_len": 35, "max_pts": 150},
    {"id": 18, "item_id": 63, "name": "Blowfish", "name_pt": "Baiacu", "max_len": 50, "max_pts": 200},
    {"id": 19, "item_id": 64, "name": "Moorfish", "name_pt": "Moorfish", "max_len": 30, "max_pts": 200},
    {"id": 20, "item_id": 65, "name": "Sea Bass", "name_pt": "Robalo do Mar", "max_len": 70, "max_pts": 280},
    {"id": 21, "item_id": 66, "name": "Flatfish", "name_pt": "Linguado / Flatfish", "max_len": 50, "max_pts": 280},
    {"id": 22, "item_id": 67, "name": "Sea Bream", "name_pt": "Pargo Vermelho", "max_len": 70, "max_pts": 300},
    {"id": 23, "item_id": 68, "name": "Octopus", "name_pt": "Polvo", "max_len": 80, "max_pts": 350},
    {"id": 24, "item_id": 69, "name": "Bonito", "name_pt": "Bonito", "max_len": 120, "max_pts": 400},
    {"id": 25, "item_id": 70, "name": "Black Porgy", "name_pt": "Sargo Preto", "max_len": 70, "max_pts": 400},
    {"id": 26, "item_id": 71, "name": "Angler", "name_pt": "Tamboril / Peixe-Pescador", "max_len": 140, "max_pts": 450},
    {"id": 27, "item_id": 72, "name": "Spearfish", "name_pt": "Peixe-Espada / Marlin", "max_len": 190, "max_pts": 500},
    {"id": 28, "item_id": 73, "name": "Whale", "name_pt": "Baleia", "max_len": 250, "max_pts": 999},
    {"id": 29, "item_id": 74, "name": "Acheron", "name_pt": "Acheron", "max_len": 50, "max_pts": 300},
]

# Fishing Rods
FISHING_RODS = [
    {"id": 0, "name": "Wooden Rod", "name_pt": "Vara de Madeira"},
    {"id": 1, "name": "Bamboo Rod", "name_pt": "Vara de Bambu"},
    {"id": 2, "name": "Deluxe Rod", "name_pt": "Vara Deluxe"},
    {"id": 3, "name": "Angling Rod", "name_pt": "Vara de Pesca Profissional"},
    {"id": 4, "name": "Spanner", "name_pt": "Chave Inglesa (Spanner)"},
    {"id": 5, "name": "Master's Rod", "name_pt": "Vara do Mestre (Master's Rod)"},
]

# Fishing Lures
FISHING_LURES = [
    {"id": 0x00, "name": "Silver Top", "name_pt": "Isca Topo Prata"},
    {"id": 0x01, "name": "Gold Top", "name_pt": "Isca Topo Ouro"},
    {"id": 0x02, "name": "Platinum Top", "name_pt": "Isca Topo Platina"},
    {"id": 0x03, "name": "Twister", "name_pt": "Twister"},
    {"id": 0x04, "name": "Warbler", "name_pt": "Warbler"},
    {"id": 0x05, "name": "Dancer", "name_pt": "Dancer"},
    {"id": 0x06, "name": "Popper", "name_pt": "Popper"},
    {"id": 0x07, "name": "Flanger", "name_pt": "Flanger"},
    {"id": 0x08, "name": "Deep Diver", "name_pt": "Mergulhador Profundo"},
    {"id": 0x09, "name": "Bottom", "name_pt": "Fundo"},
    {"id": 0x0A, "name": "Hanger", "name_pt": "Hanger"},
    {"id": 0x0B, "name": "Topper", "name_pt": "Topper"},
    {"id": 0x0C, "name": "Minnow", "name_pt": "Peixinho (Minnow)"},
    {"id": 0x0D, "name": "Frog", "name_pt": "Sapo (Frog)"},
    {"id": 0x0E, "name": "Worm", "name_pt": "Minhoca (Worm)"},
    {"id": 0x0F, "name": "Sinker", "name_pt": "Afundador (Sinker)"},
    {"id": 0x10, "name": "Float", "name_pt": "Flutuador (Float)"},
    {"id": 0x11, "name": "Coin", "name_pt": "Moeda (Coin)"},
    {"id": 0xFF, "name": "Nothing", "name_pt": "Nenhuma Isca"},
]

# Fisherman Ranks
FISHERMAN_RANKS = [
    {"id": 0, "name": "Beginner", "name_pt": "Iniciante", "min_pts": 0},
    {"id": 1, "name": "Beginner+", "name_pt": "Iniciante+", "min_pts": 1000},
    {"id": 2, "name": "Novice", "name_pt": "Novato", "min_pts": 2000},
    {"id": 3, "name": "Novice+", "name_pt": "Novato+", "min_pts": 3000},
    {"id": 4, "name": "Rodman", "name_pt": "Pescador", "min_pts": 4500},
    {"id": 5, "name": "Rodman+", "name_pt": "Pescador+", "min_pts": 6000},
    {"id": 6, "name": "Rodmaster", "name_pt": "Mestre Pescador", "min_pts": 7000},
    {"id": 7, "name": "Rodmaster+", "name_pt": "Mestre Pescador+", "min_pts": 8500},
    {"id": 8, "name": "Top Fisherman", "name_pt": "Mestre de Elite", "min_pts": 9500},
    {"id": 9, "name": "The Fish", "name_pt": "O Rei dos Peixes (The Fish)", "min_pts": 9999},
]
