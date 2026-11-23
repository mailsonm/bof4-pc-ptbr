"""Patch compiler and v2 package installer/restorer for Breath of Fire IV PC PT-BR.

Pipeline:
1. Validates all 8 translation shards under bof4_ptbr/corpus/ via bof4_ptbr.validate.
2. Rebuilds all 317 active .DAT text entries (handling button variants and BTLEND[5] <-> AB000_00[1]
   Section 0 sync) with strict (type_param, dest) matching and hard .psxseg RAM ceiling checks.
3. Synthesizes extended 16x16 & 24x24 PC PT-BR fonts for INIT.DAT[8..9] via font_builder.py
   while guaranteeing INIT.DAT[7] (item/equip/spell catalog) remains 100% untouched original English.
4. Builds the verified BOF4.exe patch spec via exe_patcher.py (VWF tables + Title/HUD/Compass).
5. Packs everything into a deterministic, zlib-compressed, non-pickle translation_v2.pkg bundle.
6. Exposes apply_v2_patch(game_dir) and restore_v2_backup(game_dir) with atomic writes,
   full backups, PE checksum verification, and exact SHA256 restoration.

Usage:
    python3 -m bof4_ptbr.build_patch [--corpus-dir ...] [--game-dir ...] [--pkg-out ...] [--allow-empty-ptbr]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
import zlib
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from bof4_ptbr.codec import (
    DEFAULT_GAME_DIR,
    TextBlock,
    decode_text_block,
    encode_text_block,
    load_vwf_tables,
)
from bof4_ptbr.dat_engine import (
    CATALOG_DEST,
    FONT_16_DEST,
    FONT_24_DEST,
    TEXT_DEST_CEILINGS,
    TYPE_PC_FONT,
    TYPE_RAM,
    DatArchive,
    build_ab000_multisection,
)
from bof4_ptbr.exe_patcher import (
    CLEAN_BOF4_EXE_SHA256,
    ExePatchError,
    build_exe_patch_spec,
    calculate_pe_checksum,
    restore_exe_backup,
    verify_pe_checksum,
)
from bof4_ptbr.extract_corpus import DEFAULT_CORPUS_DIR, REPO_ROOT, apply_btn_map
from bof4_ptbr.font_builder import (
    PTBR_VWF_16,
    PTBR_VWF_24,
    patch_init_fonts,
)
from bof4_ptbr.validate import ValidationIssue, validate_shard

PKG_MAGIC = b"BOF4PTV2"
PKG_VERSION = "2.0.0"
DEFAULT_PKG_PATH = REPO_ROOT / "bof4_ptbr" / "translation_v2.pkg"
STATUS_FILE_NAME = ".ptbr_v2_installed"
BACKUP_DIR_NAME = "DAT_BACKUP_EN"


class BuildValidationError(RuntimeError):
    """Raised when one or more corpus shards fail validation before patch compilation."""

    def __init__(self, issues: List[ValidationIssue]) -> None:
        self.issues = issues
        preview = "\n".join(f"  {iss}" for iss in issues[:20])
        more = f"\n  ... ({len(issues) - 20} more)" if len(issues) > 20 else ""
        super().__init__(f"Corpus validation failed with {len(issues)} error(s):\n{preview}{more}")


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp_ptbr_v2")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def _resolve_entry_text(entry: Dict[str, Any], allow_empty_ptbr: bool) -> str:
    if entry.get("locked", False):
        return str(entry["en"])
    ptbr = str(entry.get("ptbr", ""))
    if ptbr:
        return ptbr
    if allow_empty_ptbr:
        return str(entry["en"])
    raise ValueError(f"Unlocked entry {entry.get('id')} has empty 'ptbr'")


def _apply_exe_patch_spec_bytes(exe_bytes: bytes, spec: Dict[str, Any]) -> bytes:
    """Applies a serialized BOF4.exe patch spec from translation_v2.pkg with strict verification."""
    clean_sha = spec["clean_sha256"]
    actual_sha = hashlib.sha256(exe_bytes).hexdigest()
    if actual_sha != clean_sha:
        raise ExePatchError(
            f"BOF4.exe SHA256 mismatch: got {actual_sha}, expected {clean_sha}"
        )

    buf = bytearray(exe_bytes)
    for op in spec["ops"]:
        off = int(op["offset"])
        expected = bytes.fromhex(op["expected_hex"])
        replacement = bytes.fromhex(op["replacement_hex"])
        if len(expected) != len(replacement):
            raise ExePatchError(f"Spec op {op['name']} length mismatch")
        actual = bytes(buf[off : off + len(expected)])
        if actual != expected:
            raise ExePatchError(
                f"Pre-flight byte mismatch at {op['name']} (Raw 0x{off:06X}): "
                f"got {actual[:16].hex()}, expected {expected[:16].hex()}"
            )
        buf[off : off + len(replacement)] = replacement

    patched = bytes(buf)
    patched_sha = hashlib.sha256(patched).hexdigest()
    if patched_sha != spec["patched_sha256"]:
        raise ExePatchError(
            f"Patched BOF4.exe SHA256 mismatch: got {patched_sha}, expected {spec['patched_sha256']}"
        )
    if not verify_pe_checksum(patched):
        raise ExePatchError("Patched BOF4.exe failed PE CheckSum verification")
    return patched


def build_translation_package(
    corpus_dir: Union[str, Path] = DEFAULT_CORPUS_DIR,
    game_dir: Union[str, Path] = DEFAULT_GAME_DIR,
    pkg_path: Union[str, Path] = DEFAULT_PKG_PATH,
    *,
    allow_empty_ptbr: bool = False,
    realign_odd_prefix: bool = True,
) -> Dict[str, Any]:
    """Validates all 8 shards, rebuilds all DAT/font/EXE patches, and writes translation_v2.pkg."""
    corpus_path = Path(corpus_dir)
    gdir = Path(game_dir)
    dat_dir = gdir / "DAT"
    exe_path = gdir / "BOF4.exe"
    out_pkg = Path(pkg_path)

    if not dat_dir.is_dir() or not exe_path.is_file():
        raise FileNotFoundError(f"Clean game directory invalid: {gdir}")

    shard_files = sorted(corpus_path.glob("shard_*.json"))
    if len(shard_files) != 8:
        raise FileNotFoundError(
            f"Expected 8 corpus shards in {corpus_path}, found {len(shard_files)}"
        )

    # 1. Validate every shard against exact VWF metrics (including PT-BR font metrics)
    tables = load_vwf_tables(exe_path)
    all_issues: List[ValidationIssue] = []
    shard_docs: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    for sp in shard_files:
        doc = json.loads(sp.read_text(encoding="utf-8"))
        issues = validate_shard(doc, allow_empty_ptbr=allow_empty_ptbr, vwf_tables=tables)
        all_issues.extend(issues)
        for e in doc.get("entries", []):
            eid = str(e.get("id", ""))
            if eid in seen_ids:
                all_issues.append(
                    ValidationIssue(eid, "DUPLICATE_ID", f"Duplicate ID across shards: {eid}")
                )
            seen_ids.add(eid)
        shard_docs.append(doc)

    if all_issues:
        raise BuildValidationError(all_issues)

    # 2. Rebuild all DAT text entry payloads keyed strictly by (filename -> [(type_param, dest, bytes)])
    dat_payloads: Dict[str, Dict[Tuple[int, int], bytes]] = defaultdict(dict)
    total_translated_entries = 0
    total_locked_entries = 0

    for doc in shard_docs:
        entries_by_group: Dict[str, Dict[Tuple[int, int], Dict[str, Any]]] = defaultdict(dict)
        for e in doc["entries"]:
            entries_by_group[e["group_id"]][(int(e["section"]), int(e["slice_index"]))] = e
            if e.get("locked", False):
                total_locked_entries += 1
            elif e.get("ptbr"):
                total_translated_entries += 1

        for grp in doc["groups"]:
            gid = grp["group_id"]
            canon_file = grp["canonical_file"]
            canon_dest = int(grp["dest"])
            is_multi = bool(grp.get("is_multi_section", False))
            grp_entries = entries_by_group[gid]

            canon_arc = DatArchive.from_file(dat_dir / canon_file)
            canon_raw = canon_arc.find_text_entry(canon_dest).data

            if is_multi and canon_file == "AB000_00.DAT" and canon_dest == 0x00000:
                # Special 2-section handling: rebuild Sec0 cleanly from BTLEND.DAT[5] template
                # (zero stale 3-byte alignment pad) + Sec1 from AB000_00.DAT[1], then re-align
                btlend_arc = DatArchive.from_file(dat_dir / "BTLEND.DAT")
                btlend_raw = btlend_arc.find_text_entry(0x10000).data
                sec0_block = decode_text_block(btlend_raw, ptbr_mode=False)
                ab_block = decode_text_block(canon_raw, ptbr_mode=False)
                sec1_block = TextBlock(sections=[ab_block.sections[1]], is_multi_section=False)

                for sl in sec0_block.sections[0].slices:
                    e = grp_entries[(0, sl.index)]
                    sl.text = _resolve_entry_text(e, allow_empty_ptbr)
                for sl in sec1_block.sections[0].slices:
                    e = grp_entries[(1, sl.index)]
                    sl.text = _resolve_entry_text(e, allow_empty_ptbr)

                sec0_bytes = encode_text_block(
                    sec0_block, realign_odd_prefix=realign_odd_prefix, allow_raw=True
                )
                sec1_bytes = encode_text_block(
                    sec1_block, realign_odd_prefix=realign_odd_prefix, allow_raw=True
                )
                ab_rebuilt = build_ab000_multisection(sec0_bytes, sec1_bytes)

                if len(ab_rebuilt) > TEXT_DEST_CEILINGS[0x00000]:
                    raise ValueError(
                        f"AB000_00.DAT[1] size {len(ab_rebuilt)} exceeds 64 KiB ceiling"
                    )
                if len(sec0_bytes) > TEXT_DEST_CEILINGS[0x10000]:
                    raise ValueError(
                        f"BTLEND.DAT[5] size {len(sec0_bytes)} exceeds 64 KiB ceiling"
                    )

                dat_payloads["AB000_00.DAT"][(TYPE_RAM, 0x00000)] = ab_rebuilt
                for sync_t in grp.get("section_sync_targets", []):
                    s_file = sync_t["file"]
                    s_dest = int(sync_t["dest"])
                    dat_payloads[s_file][(TYPE_RAM, s_dest)] = sec0_bytes
                continue

            # Standard single-table group (with optional exact copies & button-icon variants)
            for target in grp["targets"]:
                t_file = target["file"]
                t_dest = int(target["dest"])
                slice_btn_maps: Dict[str, Dict[str, str]] = target.get("slice_btn_maps", {})

                blk = decode_text_block(canon_raw, ptbr_mode=False)
                for sec_idx, sec in enumerate(blk.sections):
                    for sl in sec.slices:
                        e = grp_entries[(sec_idx, sl.index)]
                        text = _resolve_entry_text(e, allow_empty_ptbr)
                        bmap = slice_btn_maps.get(f"{sec_idx}:{sl.index}")
                        if bmap:
                            text = apply_btn_map(text, bmap)
                        sl.text = text

                rebuilt = encode_text_block(
                    blk, realign_odd_prefix=realign_odd_prefix, allow_raw=True
                )
                ceiling = TEXT_DEST_CEILINGS[t_dest]
                if len(rebuilt) > ceiling:
                    raise ValueError(
                        f"Rebuilt entry {t_file} dest={t_dest:#x} is {len(rebuilt)} B "
                        f"(exceeds ceiling {ceiling} B)"
                    )
                key = (TYPE_RAM, t_dest)
                if key in dat_payloads[t_file]:
                    raise AssertionError(f"Duplicate patch target ({t_file}, {key})")
                dat_payloads[t_file][key] = rebuilt

    # 3. Synthesize extended 16x16 & 24x24 PC PT-BR fonts for INIT.DAT[8..9]
    clean_init_bytes = (dat_dir / "INIT.DAT").read_bytes()
    patched_init_fonts_bytes = patch_init_fonts(clean_init_bytes)
    patched_init_arc = DatArchive.from_bytes(patched_init_fonts_bytes, filename="INIT.DAT")
    f16_payload = patched_init_arc.find_entry(TYPE_PC_FONT, FONT_16_DEST).data
    f24_payload = patched_init_arc.find_entry(TYPE_PC_FONT, FONT_24_DEST).data
    dat_payloads["INIT.DAT"][(TYPE_PC_FONT, FONT_16_DEST)] = f16_payload
    dat_payloads["INIT.DAT"][(TYPE_PC_FONT, FONT_24_DEST)] = f24_payload

    # Hard safety check: INIT.DAT[7] (catalog) MUST NEVER be patched
    if (TYPE_RAM, CATALOG_DEST) in dat_payloads["INIT.DAT"]:
        raise AssertionError("Safety violation: INIT.DAT[7] catalog present in patch set!")

    # 4. Build verified BOF4.exe patch spec
    clean_exe_bytes = exe_path.read_bytes()
    exe_spec = build_exe_patch_spec(
        clean_exe_bytes, vwf_24=PTBR_VWF_24, vwf_16=PTBR_VWF_16
    )

    # 5. Deduplicate binary blobs in package stream for compact deterministic translation_v2.pkg
    blob_stream = bytearray()
    blob_index: Dict[str, Tuple[int, int]] = {}
    dat_patches_meta: Dict[str, List[Dict[str, Any]]] = {}
    total_dat_entries = 0

    for fname in sorted(dat_payloads.keys()):
        file_ops: List[Dict[str, Any]] = []
        for (type_param, dest), blob in sorted(dat_payloads[fname].items()):
            sha = hashlib.sha256(blob).hexdigest()
            if sha not in blob_index:
                off = len(blob_stream)
                blob_stream.extend(blob)
                blob_index[sha] = (off, len(blob))
            b_off, b_len = blob_index[sha]
            file_ops.append(
                {
                    "type_param": type_param,
                    "dest": dest,
                    "blob_off": b_off,
                    "blob_len": b_len,
                    "sha256": sha,
                }
            )
            total_dat_entries += 1
        dat_patches_meta[fname] = file_ops

    meta = {
        "format": "bof4_ptbr_v2",
        "version": PKG_VERSION,
        "exe_patch_spec": exe_spec,
        "dat_patches": dat_patches_meta,
        "stats": {
            "dat_files": len(dat_patches_meta),
            "dat_entries": total_dat_entries,
            "unique_blobs": len(blob_index),
            "translated_strings": total_translated_entries,
            "locked_strings": total_locked_entries,
            "exe_ops": len(exe_spec["ops"]),
        },
    }
    meta_bytes = json.dumps(meta, separators=(",", ":"), sort_keys=True).encode("utf-8")
    raw_body = struct.pack("<I", len(meta_bytes)) + meta_bytes + bytes(blob_stream)
    compressed = PKG_MAGIC + zlib.compress(raw_body, level=9)

    out_pkg.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(out_pkg, compressed)

    return {
        "pkg_path": str(out_pkg),
        "pkg_size": len(compressed),
        "dat_files": len(dat_patches_meta),
        "dat_entries": total_dat_entries,
        "unique_blobs": len(blob_index),
        "exe_ops": len(exe_spec["ops"]),
        "exe_patched_sha256": exe_spec["patched_sha256"],
        "pe_checksum": exe_spec["pe_checksum"],
    }


def load_v2_package(pkg_path: Union[str, Path] = DEFAULT_PKG_PATH) -> Tuple[Dict[str, Any], bytes]:
    """Loads, decompresses, and SHA256-verifies a translation_v2.pkg archive."""
    p = Path(pkg_path)
    if not p.is_file():
        raise FileNotFoundError(f"Package not found: {p}")
    raw = p.read_bytes()
    if len(raw) < len(PKG_MAGIC) + 4 or raw[: len(PKG_MAGIC)] != PKG_MAGIC:
        raise ValueError(f"Invalid translation_v2.pkg header in {p}")
    body = zlib.decompress(raw[len(PKG_MAGIC) :])
    meta_len = struct.unpack_from("<I", body, 0)[0]
    meta_bytes = body[4 : 4 + meta_len]
    blob_stream = body[4 + meta_len :]
    meta = json.loads(meta_bytes.decode("utf-8"))
    if meta.get("format") != "bof4_ptbr_v2":
        raise ValueError(f"Unexpected package format: {meta.get('format')!r}")

    # Integrity check every referenced blob
    checked: set[Tuple[int, int, str]] = set()
    for fname, ops in meta["dat_patches"].items():
        for op in ops:
            key = (op["blob_off"], op["blob_len"], op["sha256"])
            if key in checked:
                continue
            blob = blob_stream[op["blob_off"] : op["blob_off"] + op["blob_len"]]
            if len(blob) != op["blob_len"] or hashlib.sha256(blob).hexdigest() != op["sha256"]:
                raise ValueError(f"Corrupted blob in package for {fname}")
            checked.add(key)

    return meta, blob_stream


def apply_v2_patch(
    game_dir: Union[str, Path],
    pkg_path: Union[str, Path] = DEFAULT_PKG_PATH,
    *,
    create_backup: bool = True,
) -> Dict[str, Any]:
    """Applies translation_v2.pkg cleanly to game_dir with full backups and integrity checks."""
    gdir = Path(game_dir).resolve()
    dat_dir = gdir / "DAT"
    backup_dir = gdir / BACKUP_DIR_NAME
    exe_path = gdir / "BOF4.exe"

    if not exe_path.is_file() or not (dat_dir / "INIT.DAT").is_file():
        raise FileNotFoundError(f"Invalid Breath of Fire IV PC directory: {gdir}")

    meta, blob_stream = load_v2_package(pkg_path)
    dat_patches: Dict[str, List[Dict[str, Any]]] = meta["dat_patches"]
    exe_spec: Dict[str, Any] = meta["exe_patch_spec"]

    # 1. Create non-destructive backups of original English DATs & BOF4.exe
    if create_backup:
        backup_dir.mkdir(parents=True, exist_ok=True)
        for fname in sorted(dat_patches.keys()):
            src = dat_dir / fname
            bak = backup_dir / fname
            if src.is_file() and not bak.exists():
                shutil.copy2(src, bak)
        exe_bak = Path(str(exe_path) + ".bak")
        if not exe_bak.exists():
            shutil.copy2(exe_path, exe_bak)

    # 2. Patch BOF4.exe from clean source (backup if available, else current exe)
    exe_bak = Path(str(exe_path) + ".bak")
    exe_src = exe_bak if exe_bak.is_file() else exe_path
    patched_exe = _apply_exe_patch_spec_bytes(exe_src.read_bytes(), exe_spec)
    _atomic_write(exe_path, patched_exe)

    # 3. Patch every target .DAT strictly by (type_param, dest) from clean backup source
    patched_files = 0
    patched_entries = 0
    errors: List[str] = []

    for fname, ops in sorted(dat_patches.items()):
        target_path = dat_dir / fname
        backup_path = backup_dir / fname
        source_path = backup_path if backup_path.is_file() else target_path
        if not source_path.is_file():
            errors.append(f"Missing DAT file: {fname}")
            continue
        try:
            arc = DatArchive.from_file(source_path)
            for op in ops:
                blob = blob_stream[op["blob_off"] : op["blob_off"] + op["blob_len"]]
                arc.replace_entry(int(op["type_param"]), int(op["dest"]), blob)
                patched_entries += 1
            _atomic_write(target_path, arc.to_bytes())
            patched_files += 1
        except Exception as exc:
            errors.append(f"{fname}: {exc}")

    # 4. Write status manifest
    status_path = dat_dir / STATUS_FILE_NAME
    manifest = {
        "version": meta["version"],
        "patched_dat_files": sorted(dat_patches.keys()),
        "exe_patched_sha256": hashlib.sha256(patched_exe).hexdigest(),
        "pe_checksum": calculate_pe_checksum(patched_exe),
    }
    _atomic_write(status_path, json.dumps(manifest, indent=2).encode("utf-8"))

    return {
        "game_dir": str(gdir),
        "patched_dat_files": patched_files,
        "patched_dat_entries": patched_entries,
        "exe_patched_sha256": manifest["exe_patched_sha256"],
        "pe_checksum": manifest["pe_checksum"],
        "pe_checksum_valid": verify_pe_checksum(patched_exe),
        "errors": errors,
    }


def restore_v2_backup(
    game_dir: Union[str, Path],
    pkg_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Restores all backed-up English .DAT files and BOF4.exe with exact SHA256 verification."""
    gdir = Path(game_dir).resolve()
    dat_dir = gdir / "DAT"
    backup_dir = gdir / BACKUP_DIR_NAME
    exe_path = gdir / "BOF4.exe"
    status_path = dat_dir / STATUS_FILE_NAME

    if not backup_dir.is_dir():
        raise FileNotFoundError(f"Backup directory not found: {backup_dir}")

    # Determine expected DAT file set (restore ALL files in DAT_BACKUP_EN + verify manifest/pkg)
    expected_files: set[str] = {p.name for p in backup_dir.glob("*.DAT")}
    if status_path.is_file():
        try:
            manifest = json.loads(status_path.read_text(encoding="utf-8"))
            expected_files.update(manifest.get("patched_dat_files", []))
        except Exception:
            pass
    if pkg_path is not None and Path(pkg_path).is_file():
        meta, _ = load_v2_package(pkg_path)
        expected_files.update(meta["dat_patches"].keys())

    restored_files = 0
    errors: List[str] = []
    for fname in sorted(expected_files):
        bak = backup_dir / fname
        dst = dat_dir / fname
        if not bak.is_file():
            errors.append(f"Missing backup file: {fname}")
            continue
        _atomic_write(dst, bak.read_bytes())
        restored_files += 1

    # Restore BOF4.exe via exe_patcher.restore_exe_backup (verifies clean GOG SHA256)
    exe_res = restore_exe_backup(exe_path)

    if status_path.is_file():
        status_path.unlink()

    return {
        "game_dir": str(gdir),
        "restored_dat_files": restored_files,
        "exe_restored_sha256": exe_res["restored_sha256"],
        "exe_clean_match": exe_res["clean_match"],
        "errors": errors,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate shards and compile Breath of Fire IV PT-BR v2 patch package."
    )
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--game-dir", type=Path, default=DEFAULT_GAME_DIR)
    parser.add_argument("--pkg-out", type=Path, default=DEFAULT_PKG_PATH)
    parser.add_argument(
        "--allow-empty-ptbr",
        action="store_true",
        help="Allow untranslated empty 'ptbr' fields (falls back to clean EN for canary builds)",
    )
    args = parser.parse_args(argv)

    stats = build_translation_package(
        corpus_dir=args.corpus_dir,
        game_dir=args.game_dir,
        pkg_path=args.pkg_out,
        allow_empty_ptbr=args.allow_empty_ptbr,
    )
    print(
        f"Built {stats['pkg_path']} ({stats['pkg_size']:,} B): "
        f"{stats['dat_files']} DAT files ({stats['dat_entries']} entries, "
        f"{stats['unique_blobs']} unique blobs), {stats['exe_ops']} EXE ops, "
        f"PE CheckSum=0x{stats['pe_checksum']:08X}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
