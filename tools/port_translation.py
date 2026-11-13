#!/usr/bin/env python3
"""Port Breath of Fire IV PT-BR translation from PS1 (nhojunior v1.1a) to PC (GOG/Steam).

Extracts translated dialogues, menus, items, spells, and equipment from the patched
PlayStation 1 disc image and injects them into the PC DAT archives with full TOC recalculation.
Preserves all pointer tables and binary structures 100% byte-exact while translating text into
clean, natural Portuguese without needing font modifications.
"""

import os
import shutil
import struct
import sys
import time

FILE_TABLE_PATH = "/tmp/bof4-recomp/tools/file_table.tsv"
PPF_PATH = "/tmp/bof4_ps1_patch/bof4_v1.1a.ppf"
PS1_BIN_PATH = "/home/mailson/Games/breath-of-fire-iv/Breath of Fire IV [U] [SLUS-01324]/breath of fire 4.bin"
PATCHED_BIN_PATH = "/tmp/bof4_patched.bin"
PC_DAT_DIR = "/home/mailson/Games/breath-of-fire-iv/drive_c/GOG Games/Breath of Fire IV/DAT"
BACKUP_DIR = "/home/mailson/Games/breath-of-fire-iv/drive_c/GOG Games/Breath of Fire IV/DAT_BACKUP_EN"

# Translation character map (maps nhojunior's custom PS1 font glyphs to standard ASCII Portuguese)
# < (ô) -> o | > (ô) -> o | _ (ê) -> e | ` (é) -> e | [ (ã) -> a | ] (á) -> a
# { (ç) -> c | } (í) -> i | | (ó) -> o | ~ (ú) -> u | \ (â) -> a | @ (ê) -> e | ^ (ô) -> o
CHAR_MAP = {
    ord("<"): ord("o"),
    ord(">"): ord("o"),
    ord("_"): ord("e"),
    ord("`"): ord("e"),
    ord("["): ord("a"),
    ord("]"): ord("a"),
    ord("{"): ord("c"),
    ord("}"): ord("i"),
    ord("|"): ord("o"),
    ord("~"): ord("u"),
    ord("\\"): ord("a"),
    ord("@"): ord("e"),
    ord("^"): ord("o"),
}


def clean_dialogue_text(raw: bytes) -> bytes:
    """Translates dialogue strings while keeping the pointer table 100% byte-exact."""
    if len(raw) < 2:
        return raw
    first_p = struct.unpack_from("<H", raw, 0)[0]
    if first_p >= len(raw):
        return raw

    ptrs = raw[:first_p]
    strs = bytearray(raw[first_p:])
    for i, b in enumerate(strs):
        if b in CHAR_MAP:
            strs[i] = CHAR_MAP[b]
    return ptrs + bytes(strs)


def clean_init_data(raw: bytes) -> bytes:
    """Translates INIT.DAT items, weapons, armor, spells while preserving section offsets and pointers."""
    res = bytearray(raw)
    sec_offsets = struct.unpack_from("<6I", res, 0)
    for s_idx, s_off in enumerate(sec_offsets):
        s_end = sec_offsets[s_idx + 1] if s_idx + 1 < len(sec_offsets) else len(res)
        first_p = struct.unpack_from("<H", res, s_off)[0]
        str_start = s_off + first_p
        for pos in range(str_start, s_end):
            b = res[pos]
            if b in CHAR_MAP:
                res[pos] = CHAR_MAP[b]
    return bytes(res)


def ensure_patched_ps1_bin():
    """Ensures /tmp/bof4_patched.bin exists and is patched with bof4_v1.1a.ppf."""
    if os.path.isfile(PATCHED_BIN_PATH) and os.path.getsize(PATCHED_BIN_PATH) == os.path.getsize(PS1_BIN_PATH):
        print(f"[✓] Using cached patched PS1 image in RAM: {PATCHED_BIN_PATH}")
        return

    print(f"[+] Copying {PS1_BIN_PATH} to RAM ({PATCHED_BIN_PATH})...")
    shutil.copyfile(PS1_BIN_PATH, PATCHED_BIN_PATH)

    print(f"[+] Applying PPF patch {PPF_PATH}...")
    with open(PPF_PATH, "rb") as f_ppf:
        ppf_data = f_ppf.read()

    pos = 1084  # Chunk start in PPF3 with block check
    chunks_applied = 0
    with open(PATCHED_BIN_PATH, "r+b") as f_dst:
        while pos < len(ppf_data):
            offset, length = struct.unpack_from("<QB", ppf_data, pos)
            pos += 9
            chunk = ppf_data[pos : pos + length]
            pos += length
            f_dst.seek(offset)
            f_dst.write(chunk)
            chunks_applied += 1

    print(f"[✓] Applied {chunks_applied:,} patch chunks successfully!")


def extract_ps1_entry(f_bin, lba: int, entry_idx: int) -> bytes:
    """Extracts user data for a specific entry inside an EMI file on the PS1 disc."""
    f_bin.seek(lba * 2352 + 24)
    hdr = f_bin.read(2048)
    num_entries = struct.unpack_from("<I", hdr, 0)[0]
    if entry_idx >= num_entries:
        raise IndexError(f"Entry {entry_idx} out of range (max {num_entries})")

    entries = []
    for i in range(num_entries):
        sz, addr, info, typ = struct.unpack_from("<3IH", hdr, 0x10 + i * 16)
        entries.append(sz)

    cur_off = 0x800
    for i in range(entry_idx):
        cur_off += (entries[i] + 2047) & ~2047

    target_sz = entries[entry_idx]
    s_start = cur_off // 2048
    s_offset = cur_off % 2048
    sectors_needed = (s_offset + target_sz + 2047) // 2048

    data = bytearray()
    for s in range(sectors_needed):
        f_bin.seek((lba + s_start + s) * 2352 + 24)
        data.extend(f_bin.read(2048))

    return bytes(data[s_offset : s_offset + target_sz])


def inject_into_pc_dat(pc_file: str, pc_entry_idx: int, new_data: bytes):
    """Replaces entry pc_entry_idx in pc_file with new_data and recalculates TOC offsets."""
    with open(pc_file, "rb") as f:
        content = bytearray(f.read())

    num_entries = struct.unpack_from("<I", content, 0)[0] // 16
    pc_entries = []
    for i in range(num_entries):
        off, sz, addr, typ = struct.unpack_from("<4I", content, i * 16)
        pc_entries.append([off, sz, addr, typ])

    old_sz = pc_entries[pc_entry_idx][1]
    new_sz = len(new_data)
    delta = new_sz - old_sz

    off = pc_entries[pc_entry_idx][0]
    before = content[:off]
    after = content[off + old_sz :]

    # Reconstruct data
    rebuilt = before + new_data + after

    # Update TOC
    pc_entries[pc_entry_idx][1] = new_sz
    for j in range(pc_entry_idx + 1, num_entries):
        pc_entries[j][0] += delta

    for i in range(num_entries):
        struct.pack_into("<4I", rebuilt, i * 16, *pc_entries[i])

    with open(pc_file, "wb") as f:
        f.write(rebuilt)


def port_all_dialogues():
    """Main workflow to port all 375 dialogues and system files."""
    ensure_patched_ps1_bin()
    os.makedirs(BACKUP_DIR, exist_ok=True)

    # Load file table
    file_table = []
    with open(FILE_TABLE_PATH) as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 3:
                file_table.append((int(parts[0], 16), int(parts[1]), parts[2]))

    f_bin = open(PATCHED_BIN_PATH, "rb")
    patched_count = 0
    errors = []

    print("\n[+] Starting conversion and injection into PC DAT files...")
    t0 = time.time()

    for idx, lba, path in file_table:
        if not path.endswith(".EMI"):
            continue
        base_name = os.path.basename(path).replace(".EMI", ".DAT")
        pc_path = os.path.join(PC_DAT_DIR, base_name)
        if not os.path.isfile(pc_path):
            continue

        # Inspect PS1 EMI
        f_bin.seek(lba * 2352 + 24)
        hdr = f_bin.read(2048)
        if hdr[8:16] != b"MATH_TBL":
            continue

        num_emi = struct.unpack_from("<I", hdr, 0)[0]
        ps_entries = []
        for e in range(num_emi):
            sz, addr, info, typ = struct.unpack_from("<3IH", hdr, 0x10 + e * 16)
            ps_entries.append((sz, addr, info, typ))

        # Check for dialogue text entry (addr == 0x80010000)
        ps_text_e = -1
        for e, (sz, addr, info, typ) in enumerate(ps_entries):
            if addr == 0x80010000 and sz > 0:
                ps_text_e = e
                break

        if ps_text_e == -1:
            continue

        # Extract translated PS1 text
        try:
            raw_text = extract_ps1_entry(f_bin, lba, ps_text_e)
        except Exception as e:
            errors.append((base_name, f"Extract error: {e}"))
            continue

        cleaned_text = clean_dialogue_text(raw_text)

        # Locate matching PC entry
        with open(pc_path, "rb") as f_pc:
            pc_raw = f_pc.read()

        num_pc = struct.unpack_from("<I", pc_raw, 0)[0] // 16
        pc_text_e = -1

        # Match 1: first 4 bytes of pointer table
        sig4 = raw_text[:4]
        for e in range(num_pc):
            off, sz, addr, typ = struct.unpack_from("<4I", pc_raw, e * 16)
            if sz > 0 and pc_raw[off : off + 4] == sig4:
                pc_text_e = e
                break

        # Match 2: size match or text pointer heuristics
        if pc_text_e == -1:
            for e in range(num_pc):
                off, sz, addr, typ = struct.unpack_from("<4I", pc_raw, e * 16)
                if abs(sz - len(raw_text)) <= 32 and sz > 0:
                    pc_text_e = e
                    break

        if pc_text_e == -1:
            errors.append((base_name, "Could not match PC text entry index"))
            continue

        # Backup before overwriting
        backup_file = os.path.join(BACKUP_DIR, base_name)
        if not os.path.exists(backup_file):
            shutil.copyfile(pc_path, backup_file)

        # Inject into PC DAT
        try:
            inject_into_pc_dat(pc_path, pc_text_e, cleaned_text)
            patched_count += 1
            if patched_count % 50 == 0:
                print(f"  -> Patched {patched_count} files...")
        except Exception as e:
            errors.append((base_name, f"Injection error: {e}"))

    # Also patch INIT.DAT (Items, Weapons, Armors, Spells)
    try:
        init_pc = os.path.join(PC_DAT_DIR, "INIT.DAT")
        init_bak = os.path.join(BACKUP_DIR, "INIT.DAT")
        # Restore clean backup first if already backed up
        if os.path.exists(init_bak):
            shutil.copyfile(init_bak, init_pc)
        else:
            shutil.copyfile(init_pc, init_bak)

        # INIT.EMI is at sector 98975, entry 6
        raw_init = extract_ps1_entry(f_bin, 98975, 6)
        cleaned_init = clean_init_data(raw_init)
        # In PC INIT.DAT, entry 7 is the item table
        inject_into_pc_dat(init_pc, 7, cleaned_init)
        patched_count += 1
        print("[✓] Patched global item & spell catalog (INIT.DAT) successfully!")
    except Exception as e:
        errors.append(("INIT.DAT", f"INIT error: {e}"))

    f_bin.close()
    elapsed = time.time() - t0
    print(f"\n[✓] Completed! Successfully ported {patched_count} files in {elapsed:.2f} seconds!")
    print(f"[✓] Backups preserved at: {BACKUP_DIR}")
    if errors:
        print(f"[!] Skipped / Errors on {len(errors)} files: {errors[:5]}")


if __name__ == "__main__":
    port_all_dialogues()
