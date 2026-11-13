#!/usr/bin/env python3
"""Breath of Fire IV Save Editor - Command Line Interface.

Allows inspecting and modifying saves for Breath of Fire IV (PC / GOG / Steam).
"""

import argparse
import glob
import os
import sys

from bof4_save import (
    SaveFile,
    DEFAULT_SAVE_DIR,
    MAX_ZENNY,
    MAX_GP,
    FISHERMAN_RANKS,
    FISHING_RODS,
    FISHING_LURES,
)


def find_default_saves() -> list[str]:
    """Finds save files in the default game directory."""
    if not os.path.isdir(DEFAULT_SAVE_DIR):
        return []
    saves = sorted(glob.glob(os.path.join(DEFAULT_SAVE_DIR, "[0-9][0-9].DAT")))
    return saves


def print_save_info(save: SaveFile):
    """Prints a structured summary of the save file."""
    print("=" * 60)
    print(f"  BREATH OF FIRE IV - SAVE FILE OVERVIEW")
    print("=" * 60)
    print(f"Path: {save.file_path or 'In-Memory Buffer'}")
    print(f"Checksum: 0x{save.stored_checksum:02X} ({'VALID' if save.is_checksum_valid() else 'INVALID'})")
    print(f"Zenny (Money): {save.zenny:,} z")
    print(f"Game Points (GP): {save.gp:,} pts (Dragon Evolutions)")
    print("-" * 60)

    # Fishing
    rank_name = "Unknown"
    for r in FISHERMAN_RANKS:
        if r["id"] == save.fishing.rank:
            rank_name = f"{r['name']} ({r['name_pt']})"
            break

    rod_name = "Unknown"
    for rd in FISHING_RODS:
        if rd["id"] == save.fishing.rod:
            rod_name = rd["name"]
            break

    lure_name = "None"
    for lr in FISHING_LURES:
        if lr["id"] == save.fishing.lure:
            lure_name = lr["name"]
            break

    print(f"Fishing Total Score: {save.fishing.total_points:,} pts")
    print(f"Fisherman Rank: {rank_name}")
    print(f"Equipped Rod: {rod_name} | Equipped Lure: {lure_name}")
    print("-" * 60)

    # Characters
    print("PARTY MEMBERS:")
    for char in save.characters:
        name = char.name if char.name else char.default_info["default_name"]
        print(
            f"  [{char.index}] {name:8s} | Lvl {char.level:2d} | "
            f"HP: {char.current_hp:4d}/{char.total_max_hp:4d} | "
            f"AP: {char.current_ap:3d}/{char.total_max_ap:3d} | "
            f"PWR: {char.pwr:3d} DEF: {char.defense:3d} AGL: {char.agl:3d} WIS: {char.wis:3d}"
        )
    print("-" * 60)

    # Inventory count
    inv_counts = []
    for cat_idx, cat_name in enumerate(["Items", "Weapons", "Armor", "Accessories"]):
        count = sum(1 for slot in save.inventory.get_category_slots(cat_idx) if not slot["is_empty"])
        inv_counts.append(f"{cat_name}: {count}/128")
    print("INVENTORY:")
    print("  " + " | ".join(inv_counts))
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Breath of Fire IV (PC/GOG) Save Editor CLI",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("save_file", nargs="?", help="Path to save file (e.g. 01.DAT). If omitted, finds default save.")
    parser.add_argument("--info", action="store_true", help="Print save file details and exit")
    parser.add_argument("--zenny", type=int, help=f"Set Zenny amount (0 to {MAX_ZENNY:,})")
    parser.add_argument("--max-zenny", action="store_true", help="Set Zenny to maximum (99,999,999)")
    parser.add_argument("--gp", type=int, help=f"Set Game Points for Dragon forms (0 to {MAX_GP:,})")
    parser.add_argument("--max-gp", action="store_true", help="Set Game Points to 65,000 (unlocks Kaiser/Punk breaths)")
    parser.add_argument("--max-fishing", action="store_true", help="Set all 30 fish records to max, Master's Rod, The Fish rank")
    parser.add_argument("--max-stats", action="store_true", help="Set all 7 party members to Lvl 99 and 9999 HP / 999 AP / 999 Stats")
    parser.add_argument("--max-items", action="store_true", help="Set all currently owned items quantity to 99")
    parser.add_argument("--all-items", action="store_true", help="Unlock all catalog items, weapons, armors, accessories x 99")
    parser.add_argument("--god-mode", action="store_true", help="Ultimate upgrade: Max Zenny, GP, Fishing, Stats, and Items")
    parser.add_argument("--output", "-o", help="Target output file path (defaults to overwriting input file with backup)")
    parser.add_argument("--no-backup", action="store_true", help="Disable automatic .bak creation")

    args = parser.parse_args()

    # Determine file path
    save_path = args.save_file
    if not save_path:
        default_saves = find_default_saves()
        if default_saves:
            save_path = default_saves[0]
            print(f"[+] Auto-detected save file: {save_path}")
        else:
            print("[-] No save file specified and no default saves found in GOG directory.", file=sys.stderr)
            parser.print_help()
            sys.exit(1)

    if not os.path.isfile(save_path):
        print(f"[-] File not found: {save_path}", file=sys.stderr)
        sys.exit(1)

    save = SaveFile(save_path)

    if args.info or len(sys.argv) == 1:
        print_save_info(save)
        return

    # Check modifications
    modified = False

    if args.god_mode:
        print("[+] Applying God Mode (Max Zenny, GP, Fishing, Stats, Items)...")
        save.apply_god_mode(max_items_catalog=args.all_items)
        modified = True

    if args.zenny is not None:
        print(f"[+] Setting Zenny: {args.zenny:,}")
        save.zenny = args.zenny
        modified = True
    elif args.max_zenny:
        print(f"[+] Setting Zenny to MAX ({MAX_ZENNY:,})")
        save.zenny = MAX_ZENNY
        modified = True

    if args.gp is not None:
        print(f"[+] Setting Game Points: {args.gp:,}")
        save.gp = args.gp
        modified = True
    elif args.max_gp:
        print("[+] Setting Game Points to 65,000 (Dragon Evolutions)")
        save.gp = 65000
        modified = True

    if args.max_fishing:
        print("[+] Maximizing all 30 Fish Book records, Master's Rod, and 'The Fish' rank...")
        save.fishing.max_all_fishing()
        modified = True

    if args.max_stats:
        print("[+] Maximizing stats for all 7 party members...")
        for char in save.characters:
            char.max_stats()
        modified = True

    if args.all_items:
        print("[+] Unlocking all catalog items, weapons, armor, accessories (x99)...")
        save.inventory.max_all_catalog()
        modified = True
    elif args.max_items:
        print("[+] Setting existing item quantities to 99...")
        save.inventory.set_all_existing_to_max()
        modified = True

    if modified:
        output_file = args.output or save_path
        make_bak = not args.no_backup
        saved_file = save.save(output_file, make_backup=make_bak)
        print(f"[✓] Save updated successfully: {saved_file}")
        print(f"[✓] Checksum recalculated: 0x{save.stored_checksum:02X}")
    else:
        print("[!] No modifications requested. Use --info to view save, or pass modification flags.")


if __name__ == "__main__":
    main()
