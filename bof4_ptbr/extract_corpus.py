"""Corpus extractor and shard generator for Breath of Fire IV PC native PT-BR translation.

Reads all 400 non-catalog text entries from clean English PC .DAT archives (skipping INIT.DAT[7],
the 80 identical JP stubs, and 3 unused JP debug maps), deduplicates exact copies and button-icon
variants ({BTN_0..9}), syncs BTLEND.DAT[5] with AB000_00.DAT[1] Section 0, applies A2-A4 English
locks, attaches VWF pixel/line budgets, and emits 8 disjoint JSON shards under bof4_ptbr/corpus/.

Usage:
    python3 -m bof4_ptbr.extract_corpus [--dat-dir <path>] [--out-dir <path>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from bof4_ptbr.codec import (
    CONTEXT_BUDGETS,
    DEFAULT_DAT_DIR,
    TextBlock,
    TextSlice,
    count_portraits,
    decode_text_block,
    encode_text_block,
    extract_tags,
    has_legacy_jp,
)
from bof4_ptbr.dat_engine import (
    JP_DEBUG_FILES,
    JP_STUB_MD5,
    DatArchive,
    build_ab000_multisection,
    scan_dat_text_entries,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS_DIR = REPO_ROOT / "bof4_ptbr" / "corpus"

_BTN_TAG_RE = re.compile(r"\{BTN_[0-9]\}")

# Preferred canonical filenames when multiple files share a deduplicated text group
_PREFERRED_CANONICAL_RANK: Dict[str, int] = {
    "INIT.DAT": 0,
    "AB000_00.DAT": 1,
    "SGAMEN.DAT": 2,
    "CAMP.DAT": 3,
    "SHOP.DAT": 4,
    "MSHOP.DAT": 5,
    "START.DAT": 6,
    "SAVE.DAT": 7,
    "MASTER.DAT": 8,
    "AREAD075.DAT": 9,
    "AREAE024.DAT": 10,
    "D143END.DAT": 11,
    "D141BTL.DAT": 12,
    "D152BTL.DAT": 13,
}

# Explicit shard assignments for menu/UI (shard 01) and battle/descriptions/peep (shard 02)
_SHARD_01_CANONICAL_KEYS: Set[Tuple[str, int]] = {
    ("INIT.DAT", 0x10000),      # Field/chest/shop/save prompts (+BTLRET, D/E*BTL[1], SGAMENX[2])
    ("INIT.DAT", 0x27000),      # PC F9 quit/exit, HUD controls, Faerie jobs, regions/maps
    ("SGAMEN.DAT", 0x20000),    # Pause/Status/Equip/Setting menu
    ("CAMP.DAT", 0x20000),      # Camp & Master menus (+MASTER[6])
    ("SHOP.DAT", 0x20000),      # Shop menus (+COMMU03[6])
    ("MSHOP.DAT", 0x20000),     # Manillo fish shop
    ("START.DAT", 0x20000),     # Title/Save/Load/Chapter Titles/Options (+DEMO, COMMU09B, SAVE)
    ("AREAD075.DAT", 0x00000),  # Fishing UI & Options (12 AREA[12] files, 3 variants)
    ("AREAE024.DAT", 0x00000),  # Faerie Colony Management UI (5 AREAE024..028 files)
}

_SHARD_02_CANONICAL_KEYS: Set[Tuple[str, int]] = {
    ("AB000_00.DAT", 0x00000),  # Battle UI/tutorials (Sec0 + BTLEND[5]) & 189 Bestiary/Peep (Sec1)
    ("AB000_00.DAT", 0x10000),  # 567 Item/Equip/Spell descriptions (7 menu files)
    ("D141BTL.DAT", 0x00000),   # Battle story dialogue (+D142BTL, AREAD119/141/142)
    ("D152BTL.DAT", 0x00000),   # Battle story dialogue (+E077BTL, AREAD152, AREAE077, AREAM004)
    ("D143END.DAT", 0x00000),   # Post-ending clear-data save prompts
}


def _strip_all_tags(text: str) -> str:
    out = text
    for tag in set(extract_tags(text)):
        out = out.replace(tag, "")
    return out.strip()


def _normalize_btn_tags(text: str) -> str:
    return _BTN_TAG_RE.sub("{BTN_*}", text)


def _block_btn_normalized_fingerprint(block: TextBlock) -> str:
    """Computes a structural fingerprint ignoring only {BTN_0..9} button tag numbers."""
    h = hashlib.sha256()
    h.update(f"ms={int(block.is_multi_section)}|nsec={len(block.sections)}".encode("ascii"))
    for sec in block.sections:
        h.update(
            f"|ns={sec.num_slots}|pg={sec.prefix_gap.hex()}|s2s={sec.slot_to_slice}".encode("ascii")
        )
        for sl in sec.slices:
            norm = _normalize_btn_tags(sl.text)
            h.update(
                f"|{sl.index}:{int(sl.terminated)}:{sl.trailing_raw.hex()}:".encode("ascii")
            )
            h.update(norm.encode("utf-8"))
    return h.hexdigest()[:16]


def _compute_slice_btn_maps(
    canon_block: TextBlock, variant_block: TextBlock
) -> Dict[str, Dict[str, str]]:
    """Computes exact per-slice {canonical_btn: variant_btn} maps for a button variant."""
    btn_maps: Dict[str, Dict[str, str]] = {}
    if len(canon_block.sections) != len(variant_block.sections):
        raise ValueError("Variant section count mismatch")
    for sec_idx, (c_sec, v_sec) in enumerate(zip(canon_block.sections, variant_block.sections)):
        if len(c_sec.slices) != len(v_sec.slices):
            raise ValueError(f"Variant slice count mismatch in section {sec_idx}")
        for c_sl, v_sl in zip(c_sec.slices, v_sec.slices):
            if c_sl.text == v_sl.text:
                continue
            if _normalize_btn_tags(c_sl.text) != _normalize_btn_tags(v_sl.text):
                raise ValueError(
                    f"Non-button difference in section {sec_idx} slice {c_sl.index}"
                )
            c_btns = _BTN_TAG_RE.findall(c_sl.text)
            v_btns = _BTN_TAG_RE.findall(v_sl.text)
            if len(c_btns) != len(v_btns):
                raise ValueError(
                    f"Button tag count mismatch in section {sec_idx} slice {c_sl.index}"
                )
            mapping: Dict[str, str] = {}
            for cb, vb in zip(c_btns, v_btns):
                if cb in mapping and mapping[cb] != vb:
                    raise ValueError(
                        f"Non-single-valued button diff in sec {sec_idx} slice {c_sl.index}: "
                        f"{cb} -> {mapping[cb]} vs {vb}"
                    )
                mapping[cb] = vb
            # Store only when at least one tag changes
            if any(k != v for k, v in mapping.items()):
                btn_maps[f"{sec_idx}:{c_sl.index}"] = mapping
    return btn_maps


def apply_btn_map(text: str, btn_map: Optional[Dict[str, str]]) -> str:
    """Applies a simultaneous per-slice {BTN_a} -> {BTN_b} mapping without double-substitution."""
    if not btn_map:
        return text
    return _BTN_TAG_RE.sub(lambda m: btn_map.get(m.group(0), m.group(0)), text)


def _determine_lock(
    canon_file: str, dest: int, section: int, sl: TextSlice
) -> Tuple[bool, Optional[str]]:
    """Applies A2-A4 English lock rules and empty/JP-leftover locks."""
    if not _strip_all_tags(sl.text):
        return True, "empty_or_control_only"
    if has_legacy_jp(sl.text):
        return True, "unused_jp_leftover"

    slot_set = set(sl.slots)

    # CAMP.DAT[5] / MASTER.DAT[6] (dest=0x20000)
    if canon_file == "CAMP.DAT" and dest == 0x20000:
        if slot_set & set(range(158, 171)):
            return True, "master_location_en"
        if slot_set & set(range(184, 196)):
            return True, "master_name_en"
        if slot_set & set(range(196, 208)):
            return True, "master_will_en"
        if slot_set & {228, 229, 230}:
            return True, "item_name_en"
        if slot_set & set(range(208, 255)):
            return True, "master_skill_en"

    # SGAMEN.DAT[6] (dest=0x20000)
    if canon_file == "SGAMEN.DAT" and dest == 0x20000:
        if slot_set & set(range(184, 196)):
            return True, "master_name_en"
        if slot_set & set(range(196, 208)):
            return True, "master_will_en"

    # INIT.DAT[6] (dest=0x27000)
    if canon_file == "INIT.DAT" and dest == 0x27000:
        if slot_set & set(range(46, 62)):
            return True, "region_name_en"
        if slot_set & set(range(62, 124)):
            return True, "location_name_en"

    # START.DAT[5] / SAVE.DAT[6] / DEMO.DAT[2] / COMMU09B.DAT[7] (dest=0x20000)
    # Note: slots 55..68 are Chapter Titles and MUST remain unlocked!
    if canon_file == "START.DAT" and dest == 0x20000:
        if slot_set & set(range(71, 144)):
            return True, "save_location_en"

    # Fishing AREA[12] (canonical AREAD075.DAT, dest=0x0)
    if canon_file == "AREAD075.DAT" and dest == 0x00000:
        if slot_set & set(range(384, 396)):
            return True, "fishing_spot_title_en"

    return False, None


def _is_pure_choice_string(text: str) -> bool:
    """Returns True if the string contains only a choice box with no preceding prose."""
    idx = text.find("{CHOICE:")
    if idx == -1:
        idx = text.find("{CHOICE_RAW:")
    if idx == -1:
        return False
    return _strip_all_tags(text[:idx]) == ""


def _determine_context_and_budget(
    canon_file: str, dest: int, section: int, text: str
) -> Tuple[str, int, Optional[int], bool]:
    """Determines (context, max_px, max_lines, preserve_line_count) for a string slice."""
    portraits = count_portraits(text)

    if canon_file == "INIT.DAT" and dest == 0x10000:
        ctx = "choice" if _is_pure_choice_string(text) else "init_5"
        px, ml = CONTEXT_BUDGETS[ctx]
        preserve = ("\n" not in text and "{PAGE}" not in text and len(_strip_all_tags(text)) <= 18)
        return ctx, px, ml, preserve

    if canon_file == "INIT.DAT" and dest == 0x27000:
        px, ml = CONTEXT_BUDGETS["init_6"]
        return "init_6", px, ml, True

    if canon_file == "AB000_00.DAT" and dest == 0x10000:
        px, ml = CONTEXT_BUDGETS["desc"]
        return "desc", px, ml, False

    if canon_file == "AB000_00.DAT" and dest == 0x00000:
        if section == 1:
            px, ml = CONTEXT_BUDGETS["desc"]
            return "desc", px, ml, False
        if portraits >= 2:
            ctx = "battle_2p"
        elif portraits == 1:
            ctx = "battle_1p"
        elif _is_pure_choice_string(text):
            ctx = "choice"
        else:
            ctx = "battle_sys"
        px, ml = CONTEXT_BUDGETS[ctx]
        return ctx, px, ml, False

    if canon_file in ("D141BTL.DAT", "D152BTL.DAT") and dest == 0x00000:
        if portraits >= 2:
            ctx = "battle_2p"
        elif portraits == 1:
            ctx = "battle_1p"
        elif _is_pure_choice_string(text):
            ctx = "choice"
        else:
            ctx = "dialogue_0p"
        px, ml = CONTEXT_BUDGETS[ctx]
        return ctx, px, ml, False

    if (canon_file, dest) in _SHARD_01_CANONICAL_KEYS:
        if portraits >= 2:
            ctx = "dialogue_2p"
        elif portraits == 1:
            ctx = "dialogue_1p"
        elif _is_pure_choice_string(text):
            ctx = "choice"
        else:
            ctx = "menu"
        px, ml = CONTEXT_BUDGETS[ctx]
        # Preserve single-line UI labels (menus, options, chapter titles, short button labels)
        preserve = (
            ctx == "menu"
            and "\n" not in text
            and "{PAGE}" not in text
            and "{NL2}" not in text
            and len(_strip_all_tags(text)) <= 24
        )
        return ctx, px, ml, preserve

    # Standard story / map / ending dialogues
    if portraits >= 2:
        ctx = "dialogue_2p"
    elif portraits == 1:
        ctx = "dialogue_1p"
    elif _is_pure_choice_string(text):
        ctx = "choice"
    else:
        ctx = "dialogue_0p"
    px, ml = CONTEXT_BUDGETS[ctx]
    return ctx, px, ml, False


def _pick_canonical_item(
    items: List[Tuple[str, int, int, bytes, TextBlock]]
) -> Tuple[str, int, int, bytes, TextBlock]:
    return min(items, key=lambda it: (_PREFERRED_CANONICAL_RANK.get(it[0], 999), it[0], it[1]))


def extract_corpus(
    dat_dir: Path = DEFAULT_DAT_DIR,
    out_dir: Path = DEFAULT_CORPUS_DIR,
) -> Dict[str, Any]:
    """Extracts all translatable PC .DAT text blocks into 8 balanced, disjoint JSON shards.

    Returns summary statistics dict for all generated shards.
    """
    dat_dir = Path(dat_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    scanned = scan_dat_text_entries(dat_dir, include_catalog=False)
    if len(scanned) != 400:
        raise RuntimeError(f"Expected 400 non-catalog text entries in {dat_dir}, found {len(scanned)}")

    # Load all active non-stub, non-JP-debug entries
    active_items: List[Tuple[str, int, int, bytes, TextBlock]] = []
    skipped_jp_stubs = 0
    skipped_jp_debug = 0
    btlend_item: Optional[Tuple[str, int, int, bytes, TextBlock]] = None

    for fname, entry_idx, dest, _sz in scanned:
        arc = DatArchive.from_file(dat_dir / fname)
        raw = arc.find_text_entry(dest).data
        md5 = hashlib.md5(raw).hexdigest()
        if dest == 0 and md5 == JP_STUB_MD5:
            skipped_jp_stubs += 1
            continue
        if fname in JP_DEBUG_FILES:
            skipped_jp_debug += 1
            continue
        block = decode_text_block(raw, ptbr_mode=False)
        if fname == "BTLEND.DAT" and dest == 0x10000:
            btlend_item = (fname, entry_idx, dest, raw, block)
            continue
        active_items.append((fname, entry_idx, dest, raw, block))

    # Deduplicate by (dest, button-normalized structural fingerprint)
    grouped: Dict[Tuple[int, str], List[Tuple[str, int, int, bytes, TextBlock]]] = defaultdict(list)
    for item in active_items:
        fname, entry_idx, dest, raw, block = item
        fp = _block_btn_normalized_fingerprint(block)
        grouped[(dest, fp)].append(item)

    # Build group descriptors + entries
    group_records: List[Dict[str, Any]] = []
    for (dest, fp), items in sorted(grouped.items()):
        canon_file, canon_idx, canon_dest, canon_raw, canon_block = _pick_canonical_item(items)
        group_id = f"{canon_file}:0x{canon_dest:X}"

        targets: List[Dict[str, Any]] = []
        for fname, entry_idx, t_dest, raw, blk in sorted(items, key=lambda x: (x[0], x[1])):
            if raw == canon_raw:
                targets.append(
                    {
                        "file": fname,
                        "entry_index": entry_idx,
                        "dest": t_dest,
                        "exact_copy": True,
                        "slice_btn_maps": {},
                    }
                )
            else:
                btn_maps = _compute_slice_btn_maps(canon_block, blk)
                # Self-verify lossless variant reconstruction on clean English right now!
                test_block = decode_text_block(canon_raw, ptbr_mode=False)
                for s_i, sec in enumerate(test_block.sections):
                    for sl in sec.slices:
                        bmap = btn_maps.get(f"{s_i}:{sl.index}")
                        if bmap:
                            sl.text = apply_btn_map(sl.text, bmap)
                rebuilt_var = encode_text_block(test_block)
                if rebuilt_var != raw:
                    raise AssertionError(
                        f"Variant round-trip self-check failed for {fname}[{entry_idx}] vs {canon_file}"
                    )
                targets.append(
                    {
                        "file": fname,
                        "entry_index": entry_idx,
                        "dest": t_dest,
                        "exact_copy": False,
                        "slice_btn_maps": btn_maps,
                    }
                )

        # Attach BTLEND.DAT[5] as section-0 sync target on AB000_00.DAT[1]
        section_sync_targets: List[Dict[str, Any]] = []
        if canon_file == "AB000_00.DAT" and canon_dest == 0x00000:
            if btlend_item is None:
                raise RuntimeError("Missing BTLEND.DAT[5] for AB000_00.DAT[1] Section 0 sync")
            be_fn, be_idx, be_dest, be_raw, be_blk = btlend_item
            # Verify BTLEND[5] matches AB000_00[1] Section 0 slices 1:1 (only 3-byte 4B-align pad differs)
            ab_sec0 = canon_block.sections[0]
            be_sec = be_blk.sections[0]
            if (
                ab_sec0.num_slots != be_sec.num_slots
                or ab_sec0.slot_to_slice != be_sec.slot_to_slice
                or len(ab_sec0.slices) != len(be_sec.slices)
                or any(
                    a.text != b.text or a.slots != b.slots
                    for a, b in zip(ab_sec0.slices, be_sec.slices)
                )
            ):
                raise AssertionError("AB000_00[1] Sec0 slices diverge from BTLEND[5]")
            ab_sec0_bytes = encode_text_block(
                TextBlock(sections=[ab_sec0], is_multi_section=False)
            )
            ab_sec1_bytes = encode_text_block(
                TextBlock(sections=[canon_block.sections[1]], is_multi_section=False)
            )
            if not ab_sec0_bytes.startswith(be_raw) or any(
                b != 0 for b in ab_sec0_bytes[len(be_raw) :]
            ):
                raise AssertionError(
                    f"AB000_00[1] Sec0 ({len(ab_sec0_bytes)}B) != BTLEND[5] ({len(be_raw)}B) + zero pad"
                )
            if build_ab000_multisection(be_raw, ab_sec1_bytes) != canon_raw:
                raise AssertionError("AB000_00[1] multi-section rebuild check failed")
            section_sync_targets.append(
                {
                    "file": be_fn,
                    "entry_index": be_idx,
                    "dest": be_dest,
                    "section": 0,
                }
            )

        # Build corpus entry records for every slice in every section of canonical block
        entries: List[Dict[str, Any]] = []
        unlocked_count = 0
        for sec_idx, sec in enumerate(canon_block.sections):
            for sl in sec.slices:
                locked, lock_reason = _determine_lock(canon_file, canon_dest, sec_idx, sl)
                ctx, max_px, max_lines, preserve_lc = _determine_context_and_budget(
                    canon_file, canon_dest, sec_idx, sl.text
                )
                eid = f"{canon_file}:{canon_idx}:{sec_idx}:{sl.index}"
                rec: Dict[str, Any] = {
                    "id": eid,
                    "group_id": group_id,
                    "file": canon_file,
                    "entry_index": canon_idx,
                    "dest": canon_dest,
                    "section": sec_idx,
                    "slice_index": sl.index,
                    "slots": list(sl.slots),
                    "context": ctx,
                    "max_px": max_px,
                    "max_lines": max_lines,
                    "preserve_line_count": preserve_lc,
                    "locked": locked,
                    "en": sl.text,
                    "ptbr": sl.text if locked else "",
                }
                if lock_reason is not None:
                    rec["lock_reason"] = lock_reason
                entries.append(rec)
                if not locked:
                    unlocked_count += 1

        group_records.append(
            {
                "group_id": group_id,
                "canonical_file": canon_file,
                "canonical_entry_index": canon_idx,
                "dest": canon_dest,
                "is_multi_section": canon_block.is_multi_section,
                "targets": targets,
                "section_sync_targets": section_sync_targets,
                "entries": entries,
                "unlocked_count": unlocked_count,
            }
        )

    # Partition groups into 8 disjoint shards
    shard_groups: Dict[str, List[Dict[str, Any]]] = {
        "shard_01_menus_ui": [],
        "shard_02_battle_desc_peep": [],
        "shard_03_story_1": [],
        "shard_04_story_2": [],
        "shard_05_story_3": [],
        "shard_06_story_4": [],
        "shard_07_story_5": [],
        "shard_08_story_6": [],
    }
    story_groups: List[Dict[str, Any]] = []

    for grp in group_records:
        key = (grp["canonical_file"], grp["dest"])
        if key in _SHARD_01_CANONICAL_KEYS:
            shard_groups["shard_01_menus_ui"].append(grp)
        elif key in _SHARD_02_CANONICAL_KEYS:
            shard_groups["shard_02_battle_desc_peep"].append(grp)
        else:
            story_groups.append(grp)

    # Verify all explicit keys were found
    if len(shard_groups["shard_01_menus_ui"]) != len(_SHARD_01_CANONICAL_KEYS):
        found = {(g["canonical_file"], g["dest"]) for g in shard_groups["shard_01_menus_ui"]}
        raise RuntimeError(f"Shard 01 key mismatch: missing {_SHARD_01_CANONICAL_KEYS - found}")
    if len(shard_groups["shard_02_battle_desc_peep"]) != len(_SHARD_02_CANONICAL_KEYS):
        found = {(g["canonical_file"], g["dest"]) for g in shard_groups["shard_02_battle_desc_peep"]}
        raise RuntimeError(f"Shard 02 key mismatch: missing {_SHARD_02_CANONICAL_KEYS - found}")

    # Greedy LPT bin packing of story groups across shards 03..08 for balanced unlocked string counts
    story_shard_names = [f"shard_0{i}_story_{i - 2}" for i in range(3, 9)]
    shard_loads = {name: 0 for name in story_shard_names}
    for grp in sorted(story_groups, key=lambda g: (-g["unlocked_count"], g["canonical_file"])):
        lightest = min(story_shard_names, key=lambda n: (shard_loads[n], n))
        shard_groups[lightest].append(grp)
        shard_loads[lightest] += grp["unlocked_count"]

    # Sort groups cleanly within each shard and write JSON files
    summary_shards: List[Dict[str, Any]] = []
    all_entry_ids: Set[str] = set()
    all_target_keys: Set[Tuple[str, int]] = set()

    for shard_id in sorted(shard_groups.keys()):
        grps = sorted(
            shard_groups[shard_id],
            key=lambda g: (_PREFERRED_CANONICAL_RANK.get(g["canonical_file"], 999), g["canonical_file"], g["dest"]),
        )
        shard_meta_groups: List[Dict[str, Any]] = []
        shard_entries: List[Dict[str, Any]] = []
        unlocked_total = 0
        locked_total = 0

        for grp in grps:
            for t in grp["targets"]:
                tkey = (t["file"], t["dest"])
                if tkey in all_target_keys:
                    raise AssertionError(f"Duplicate target key across shards: {tkey}")
                all_target_keys.add(tkey)
            for st in grp["section_sync_targets"]:
                tkey = (st["file"], st["dest"])
                if tkey in all_target_keys:
                    raise AssertionError(f"Duplicate sync target key across shards: {tkey}")
                all_target_keys.add(tkey)

            shard_meta_groups.append(
                {
                    "group_id": grp["group_id"],
                    "canonical_file": grp["canonical_file"],
                    "canonical_entry_index": grp["canonical_entry_index"],
                    "dest": grp["dest"],
                    "is_multi_section": grp["is_multi_section"],
                    "targets": grp["targets"],
                    "section_sync_targets": grp["section_sync_targets"],
                }
            )
            for e in grp["entries"]:
                if e["id"] in all_entry_ids:
                    raise AssertionError(f"Duplicate entry id across shards: {e['id']}")
                all_entry_ids.add(e["id"])
                shard_entries.append(e)
                if e["locked"]:
                    locked_total += 1
                else:
                    unlocked_total += 1

        shard_doc = {
            "shard_id": shard_id,
            "version": 2,
            "groups": shard_meta_groups,
            "entries": shard_entries,
        }
        shard_path = out_dir / f"{shard_id}.json"
        shard_path.write_text(
            json.dumps(shard_doc, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        summary_shards.append(
            {
                "shard_id": shard_id,
                "path": str(shard_path),
                "groups": len(shard_meta_groups),
                "dat_targets": sum(
                    len(g["targets"]) + len(g["section_sync_targets"]) for g in shard_meta_groups
                ),
                "total_entries": len(shard_entries),
                "unlocked_entries": unlocked_total,
                "locked_entries": locked_total,
            }
        )

    # Sanity check: all 400 non-catalog text entries accounted for!
    accounted = len(all_target_keys) + skipped_jp_stubs + skipped_jp_debug
    if accounted != 400:
        raise AssertionError(
            f"Accounted entries mismatch: {len(all_target_keys)} active + "
            f"{skipped_jp_stubs} stubs + {skipped_jp_debug} debug = {accounted} != 400"
        )

    return {
        "total_scanned_non_catalog": len(scanned),
        "active_dat_targets": len(all_target_keys),
        "skipped_jp_stubs": skipped_jp_stubs,
        "skipped_jp_debug": skipped_jp_debug,
        "total_groups": len(group_records),
        "total_entries": len(all_entry_ids),
        "total_unlocked": sum(s["unlocked_entries"] for s in summary_shards),
        "total_locked": sum(s["locked_entries"] for s in summary_shards),
        "shards": summary_shards,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract Breath of Fire IV PC text corpus into 8 disjoint PT-BR shards."
    )
    parser.add_argument("--dat-dir", type=Path, default=DEFAULT_DAT_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    args = parser.parse_args(argv)

    stats = extract_corpus(dat_dir=args.dat_dir, out_dir=args.out_dir)
    print(
        f"Extracted {stats['total_groups']} groups ({stats['active_dat_targets']} DAT entries; "
        f"skipped {stats['skipped_jp_stubs']} JP stubs + {stats['skipped_jp_debug']} JP debug maps):"
    )
    for s in stats["shards"]:
        print(
            f"  {s['shard_id']:26s}: groups={s['groups']:2d}, targets={s['dat_targets']:3d}, "
            f"total={s['total_entries']:4d}, unlocked={s['unlocked_entries']:4d}, locked={s['locked_entries']:4d}"
        )
    print(
        f"TOTAL: entries={stats['total_entries']}, unlocked={stats['total_unlocked']}, "
        f"locked={stats['total_locked']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
