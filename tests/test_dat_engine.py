"""Unit & integration tests for dat_engine, extract_corpus, and build_patch."""

import hashlib
import json
import os
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

from bof4_ptbr.build_patch import (
    BuildValidationError,
    apply_v2_patch,
    build_translation_package,
    load_v2_package,
    restore_v2_backup,
)
from bof4_ptbr.codec import decode_text_block, encode_ptbr_string, load_vwf_tables
from bof4_ptbr.dat_engine import (
    CATALOG_DEST,
    FONT_16_DEST,
    FONT_24_DEST,
    JP_DEBUG_FILES,
    JP_STUB_MD5,
    TEXT_DEST_CEILINGS,
    TYPE_PC_FONT,
    TYPE_RAM,
    DatArchive,
    build_ab000_multisection,
    scan_dat_text_entries,
    split_multisection,
)
from bof4_ptbr.exe_patcher import CLEAN_BOF4_EXE_SHA256, verify_pe_checksum
from bof4_ptbr.extract_corpus import DEFAULT_CORPUS_DIR, extract_corpus
from bof4_ptbr.validate import validate_shard

GAME_DIR = Path(
    "/home/mailson/Games/breath-of-fire-iv/drive_c/GOG Games/Breath of Fire IV"
)
DAT_DIR = GAME_DIR / "DAT"
EXE_PATH = GAME_DIR / "BOF4.exe"


class TestDatEngine(unittest.TestCase):
    """Tests for PC .DAT binary container parsing, matching, validation, and writing."""

    def test_all_972_clean_dat_files_round_trip_byte_exact(self):
        """Every single one of the 972 clean .DAT files must parse and re-pack byte-exact."""
        dat_files = sorted(DAT_DIR.glob("*.DAT"))
        self.assertEqual(len(dat_files), 972)

        total_entries = 0
        for dat_path in dat_files:
            raw = dat_path.read_bytes()
            arc = DatArchive.from_bytes(raw, filename=dat_path.name)
            total_entries += len(arc.entries)
            rebuilt = arc.to_bytes()
            self.assertEqual(
                rebuilt,
                raw,
                f"Round-trip mismatch in {dat_path.name}",
            )
            # Verify 0 gaps and 0 trailing pad invariant
            expected_off = len(arc.entries) * 16
            for entry in arc.entries:
                self.assertEqual(entry.offset, expected_off)
                self.assertEqual(entry.size, len(entry.data))
                expected_off += entry.size
            self.assertEqual(expected_off, len(raw))

        self.assertEqual(total_entries, 6992)

    def test_scan_dat_text_entries_exact_counts(self):
        """Strict (type_param=0, dest in TEXT_DEST_CEILINGS) scan finds 400/401 entries."""
        entries_no_cat = scan_dat_text_entries(DAT_DIR, include_catalog=False)
        entries_with_cat = scan_dat_text_entries(DAT_DIR, include_catalog=True)
        self.assertEqual(len(entries_no_cat), 400)
        self.assertEqual(len(entries_with_cat), 401)

        # Verify INIT.DAT[7] (dest=0x28000) is excluded by default and included with flag
        cat_only = set(entries_with_cat) - set(entries_no_cat)
        self.assertEqual(len(cat_only), 1)
        fname, idx, dest, sz = next(iter(cat_only))
        self.assertEqual((fname, idx, dest, sz), ("INIT.DAT", 7, 0x28000, 7940))

    def test_strict_type_dest_matching_prevents_btl_match1_collision(self):
        """D141/142/152BTL & E077BTL must resolve dest=0x0 distinctly from entry[1] dest=0x10000."""
        expected_zero_idx = {
            "D141BTL.DAT": 13,
            "D142BTL.DAT": 13,
            "D152BTL.DAT": 18,
            "E077BTL.DAT": 15,
        }
        for fname, exp_idx in expected_zero_idx.items():
            arc = DatArchive.from_file(DAT_DIR / fname)
            e_sys = arc.find_text_entry(0x10000)
            e_dlg = arc.find_text_entry(0x00000)
            self.assertEqual(e_sys.index, 1)
            self.assertEqual(e_dlg.index, exp_idx)
            # Both start with 00 02 00 02, proving sig4 matching would have failed
            self.assertEqual(e_sys.data[:4], b"\x00\x02\x00\x02")
            self.assertEqual(e_dlg.data[:4], b"\x00\x02\x00\x02")

    def test_missing_type_dest_raises_key_error(self):
        """No fallback heuristics: missing (type_param, dest) must raise KeyError."""
        arc = DatArchive.from_file(DAT_DIR / "AREAB000.DAT")
        with self.assertRaises(KeyError):
            arc.find_text_entry(0x00000)
        with self.assertRaises(KeyError):
            arc.find_entry(TYPE_PC_FONT, FONT_24_DEST)

    def test_replace_entry_preserves_order_and_recalculates_packed_offsets(self):
        """Replacing an entry with odd delta shifts subsequent offsets with 0 gaps."""
        arc = DatArchive.from_file(DAT_DIR / "AREAD001.DAT")
        orig_entries = [(e.index, e.type_param, e.dest, e.data) for e in arc.entries]
        text_entry = arc.find_text_entry(0x00000)
        orig_idx = text_entry.index
        orig_sz = text_entry.size

        # Grow by +13 bytes (odd delta)
        grown_payload = text_entry.data + (b"\x00" * 13)
        replaced_idx = arc.replace_entry(TYPE_RAM, 0x00000, grown_payload)
        self.assertEqual(replaced_idx, orig_idx)

        rebuilt = arc.to_bytes()
        reparsed = DatArchive.from_bytes(rebuilt, filename="AREAD001.DAT")
        self.assertEqual(len(reparsed.entries), len(orig_entries))
        self.assertEqual(len(rebuilt), (DAT_DIR / "AREAD001.DAT").stat().st_size + 13)

        for i, (o_idx, o_tp, o_dest, o_data) in enumerate(orig_entries):
            e = reparsed.entries[i]
            self.assertEqual((e.index, e.type_param, e.dest), (o_idx, o_tp, o_dest))
            if i == orig_idx:
                self.assertEqual(e.size, orig_sz + 13)
                self.assertEqual(e.data, grown_payload)
            else:
                # Portraits and all other entries remain 100% byte-identical
                self.assertEqual(e.data, o_data)

    def test_ram_ceilings_enforced(self):
        """Exceeding .psxseg RAM ceiling for any text dest must raise ValueError."""
        cases = [
            ("AREAD001.DAT", 0x00000, TEXT_DEST_CEILINGS[0x00000]),
            ("INIT.DAT", 0x10000, TEXT_DEST_CEILINGS[0x10000]),
            ("SGAMEN.DAT", 0x20000, TEXT_DEST_CEILINGS[0x20000]),
            ("INIT.DAT", 0x27000, TEXT_DEST_CEILINGS[0x27000]),
        ]
        for fname, dest, ceiling in cases:
            arc = DatArchive.from_file(DAT_DIR / fname)
            # Exactly at ceiling passes
            arc.replace_entry(TYPE_RAM, dest, b"\x00" * ceiling)
            # Ceiling + 1 fails
            with self.assertRaises(ValueError):
                arc.replace_entry(TYPE_RAM, dest, b"\x00" * (ceiling + 1))

    def test_init_catalog_locked_by_default(self):
        """INIT.DAT[7] (dest=0x28000) is protected against accidental overwrite."""
        arc = DatArchive.from_file(DAT_DIR / "INIT.DAT")
        orig_cat = arc.find_text_entry(0x28000).data
        with self.assertRaises(PermissionError):
            arc.replace_entry(TYPE_RAM, 0x28000, orig_cat)
        # Explicit opt-in still enforces ceiling
        arc.replace_entry(TYPE_RAM, 0x28000, orig_cat, allow_catalog=True)
        with self.assertRaises(ValueError):
            arc.replace_entry(
                TYPE_RAM,
                0x28000,
                b"\x00" * (TEXT_DEST_CEILINGS[0x28000] + 1),
                allow_catalog=True,
            )

    def test_init_font_replacement_validates_glyph_stride(self):
        """INIT.DAT[8] (16x16=128B) and [9] (24x24=288B) accept valid extended fonts and reject bad sizes."""
        arc = DatArchive.from_file(DAT_DIR / "INIT.DAT")
        f16 = arc.find_entry(TYPE_PC_FONT, FONT_16_DEST)
        f24 = arc.find_entry(TYPE_PC_FONT, FONT_24_DEST)
        self.assertEqual(f16.index, 8)
        self.assertEqual(f24.index, 9)

        # Appending 26 PT-BR glyphs succeeds
        arc.replace_entry(TYPE_PC_FONT, FONT_16_DEST, f16.data + b"\x00" * (26 * 128))
        arc.replace_entry(TYPE_PC_FONT, FONT_24_DEST, f24.data + b"\x00" * (26 * 288))
        # Non-multiple size rejected
        with self.assertRaises(ValueError):
            arc.replace_entry(TYPE_PC_FONT, FONT_16_DEST, f16.data + b"\x00" * 5)
        with self.assertRaises(ValueError):
            arc.replace_entry(TYPE_PC_FONT, FONT_24_DEST, f24.data + b"\x00" * 7)

    def test_ab000_multisection_alignment_and_btlend_sync(self):
        """AB000_00.DAT[1] rebuilds byte-identical from BTLEND.DAT[5] + Sec1 and enforces 4-byte alignment."""
        ab_arc = DatArchive.from_file(DAT_DIR / "AB000_00.DAT")
        be_arc = DatArchive.from_file(DAT_DIR / "BTLEND.DAT")

        ab_raw = ab_arc.find_text_entry(0x00000).data
        be_raw = be_arc.find_text_entry(0x10000).data

        sec0_padded, sec1 = split_multisection(ab_raw, 2)
        self.assertTrue(sec0_padded.startswith(be_raw))
        self.assertEqual(sec0_padded[len(be_raw) :], b"\x00\x00\x00")

        rebuilt_ab = build_ab000_multisection(be_raw, sec1)
        self.assertEqual(rebuilt_ab, ab_raw)

        # Misaligned s1 rejected by replace_entry on AB000_00.DAT dest=0x0
        bad_ab = struct.pack("<2I", 8, 13) + b"\x00" * 32
        with self.assertRaises(ValueError):
            ab_arc.replace_entry(TYPE_RAM, 0x00000, bad_ab)

        # Properly aligned rebuilt payload succeeds
        ab_arc.replace_entry(TYPE_RAM, 0x00000, rebuilt_ab)
        self.assertEqual(ab_arc.to_bytes(), (DAT_DIR / "AB000_00.DAT").read_bytes())

    def test_jp_stub_and_debug_constants_match_clean_corpus(self):
        """Confirm JP_STUB_MD5 matches exactly 80 files and JP_DEBUG_FILES exist."""
        stub_count = 0
        for dat_path in sorted(DAT_DIR.glob("*.DAT")):
            arc = DatArchive.from_file(dat_path)
            for e in arc.find_all_text_entries():
                if e.dest == 0 and hashlib.md5(e.data).hexdigest() == JP_STUB_MD5:
                    stub_count += 1
        self.assertEqual(stub_count, 80)
        for dbg in JP_DEBUG_FILES:
            self.assertTrue((DAT_DIR / dbg).is_file())

    def test_write_file_atomic_roundtrip(self):
        """Writing to a temp path produces exact binary match."""
        arc = DatArchive.from_file(DAT_DIR / "INIT.DAT")
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "INIT.DAT"
            arc.write_file(out_path)
            self.assertEqual(out_path.read_bytes(), (DAT_DIR / "INIT.DAT").read_bytes())


class TestExtractCorpusAndBuildPatch(unittest.TestCase):
    """Integration tests for corpus shard extraction, A2-A4 locks, v2 packaging, apply & restore."""

    def test_generated_8_shards_disjoint_balanced_and_locked(self):
        """All 8 shards under bof4_ptbr/corpus/ are disjoint, balanced, valid, and A2-A4 locked."""
        shard_paths = sorted(DEFAULT_CORPUS_DIR.glob("shard_*.json"))
        self.assertEqual(len(shard_paths), 8)
        expected_names = [
            "shard_01_menus_ui.json",
            "shard_02_battle_desc_peep.json",
            "shard_03_story_1.json",
            "shard_04_story_2.json",
            "shard_05_story_3.json",
            "shard_06_story_4.json",
            "shard_07_story_5.json",
            "shard_08_story_6.json",
        ]
        self.assertEqual([p.name for p in shard_paths], expected_names)

        tables = load_vwf_tables(EXE_PATH)
        seen_ids = set()
        seen_targets = set()
        story_unlocked_counts = []

        for sp in shard_paths:
            doc = json.loads(sp.read_text(encoding="utf-8"))
            self.assertEqual(validate_shard(doc, allow_empty_ptbr=True, vwf_tables=tables), [])
            for grp in doc["groups"]:
                for t in grp["targets"]:
                    tkey = (t["file"], int(t["dest"]))
                    self.assertNotIn(tkey, seen_targets, f"Duplicate target {tkey}")
                    seen_targets.add(tkey)
                for st in grp.get("section_sync_targets", []):
                    tkey = (st["file"], int(st["dest"]))
                    self.assertNotIn(tkey, seen_targets, f"Duplicate sync target {tkey}")
                    seen_targets.add(tkey)
            unlocked = 0
            for e in doc["entries"]:
                self.assertNotIn(e["id"], seen_ids, f"Duplicate ID {e['id']}")
                seen_ids.add(e["id"])
                self.assertNotEqual(
                    (e["file"], int(e["dest"])),
                    ("INIT.DAT", CATALOG_DEST),
                    "INIT.DAT[7] must never be extracted",
                )
                if not e["locked"]:
                    unlocked += 1
            if sp.name.startswith("shard_0") and "_story_" in sp.name:
                story_unlocked_counts.append(unlocked)

        # 317 active + 80 JP stubs + 3 JP debug maps = 400 non-catalog entries
        self.assertEqual(len(seen_targets), 317)
        # Story shards balanced within <= 5 strings of each other
        self.assertLessEqual(max(story_unlocked_counts) - min(story_unlocked_counts), 5)

        # Spot-check A2-A4 lock enforcement in shard_01
        s1 = json.loads((DEFAULT_CORPUS_DIR / "shard_01_menus_ui.json").read_text(encoding="utf-8"))
        for e in s1["entries"]:
            slots = set(e["slots"])
            if e["file"] == "CAMP.DAT" and e["dest"] == 0x20000:
                if slots & (set(range(158, 171)) | set(range(184, 255))):
                    self.assertTrue(e["locked"], f"CAMP slot {slots} must be locked")
                if slots & set(range(171, 183)):
                    self.assertFalse(e["locked"], f"CAMP Will desc {slots} should be unlocked")
            if e["file"] == "SGAMEN.DAT" and e["dest"] == 0x20000:
                if slots & set(range(184, 208)):
                    self.assertTrue(e["locked"], f"SGAMEN slot {slots} must be locked")
            if e["file"] == "INIT.DAT" and e["dest"] == 0x27000:
                if slots & set(range(46, 124)):
                    self.assertTrue(e["locked"], f"INIT[6] slot {slots} must be locked")
            if e["file"] == "START.DAT" and e["dest"] == 0x20000:
                if slots & set(range(55, 69)):
                    self.assertFalse(e["locked"], f"START Chapter Title {slots} must stay unlocked")
                if slots & set(range(71, 144)):
                    self.assertTrue(e["locked"], f"START Save location {slots} must be locked")
            if e["file"] == "AREAD075.DAT" and e["dest"] == 0x00000:
                if slots & set(range(384, 396)):
                    self.assertTrue(e["locked"], f"Fishing spot title {slots} must be locked")

    def test_canary_build_apply_verify_and_restore_cycle(self):
        """End-to-end canary: inject PT-BR samples, build pkg, apply to temp game copy, verify, restore."""
        with tempfile.TemporaryDirectory() as td:
            tmp_root = Path(td)
            tmp_corpus = tmp_root / "corpus"
            shutil.copytree(DEFAULT_CORPUS_DIR, tmp_corpus)

            # Inject real accented PT-BR sample strings into shards 01, 02, and a story shard
            s1_path = tmp_corpus / "shard_01_menus_ui.json"
            s1 = json.loads(s1_path.read_text(encoding="utf-8"))
            found_init5_btn = False
            for e in s1["entries"]:
                if e["file"] == "INIT.DAT" and e["dest"] == 0x10000 and 19 in e["slots"]:
                    # Button-variant test: INIT[5] has {BTN_1}/{BTN_2}, SGAMENX[2] maps to {BTN_0}/{BTN_1}
                    e["ptbr"] = "Cima/Baixo: Escolher ação\n{BTN_1}: Confirmar  {BTN_2}: Sair"
                    found_init5_btn = True
                    break
            self.assertTrue(found_init5_btn)
            s1_path.write_text(json.dumps(s1, ensure_ascii=False, indent=2), encoding="utf-8")

            s2_path = tmp_corpus / "shard_02_battle_desc_peep.json"
            s2 = json.loads(s2_path.read_text(encoding="utf-8"))
            found_ab_sec0 = False
            for e in s2["entries"]:
                if e["file"] == "AB000_00.DAT" and e["dest"] == 0 and e["section"] == 0 and not e["locked"]:
                    if "{IV}" in e["en"]:
                        # Sync test: AB000_00[1] Sec0 <-> BTLEND[5]
                        e["ptbr"] = (
                            "{WIN:02}Em BREATH OF FIRE {IV}, todos\n"
                            "os membros do grupo podem\n"
                            "participar do combate.{PAGE}"
                            "Escolha um comando no menu\n"
                            "para definir sua ação.{GOTO:0C:20}"
                        )
                        found_ab_sec0 = True
                        break
            self.assertTrue(found_ab_sec0)
            s2_path.write_text(json.dumps(s2, ensure_ascii=False, indent=2), encoding="utf-8")

            # Find AREAD000.DAT:8:0:2 in story shards to test portrait + accent preservation
            found_dlg = False
            for sp in sorted(tmp_corpus.glob("shard_0*_story_*.json")):
                sd = json.loads(sp.read_text(encoding="utf-8"))
                for e in sd["entries"]:
                    if e["file"] == "AREAD000.DAT" and "{PORTRAIT:C2:40}" in e["en"]:
                        e["ptbr"] = (
                            '{WIN:04}{PORTRAIT:C2:40}"Ouvi dizer que\n'
                            'havia muita gente\n'
                            'trabalhando aqui,{PAGE}'
                            'mas não vejo\n'
                            'ninguém!"'
                        )
                        found_dlg = True
                        break
                if found_dlg:
                    sp.write_text(json.dumps(sd, ensure_ascii=False, indent=2), encoding="utf-8")
                    break
            self.assertTrue(found_dlg)

            # 1. Build translation_v2.pkg
            pkg_out = tmp_root / "translation_v2.pkg"
            build_stats = build_translation_package(
                corpus_dir=tmp_corpus,
                game_dir=GAME_DIR,
                pkg_path=pkg_out,
                allow_empty_ptbr=True,
            )
            self.assertTrue(pkg_out.is_file())
            self.assertEqual(build_stats["dat_entries"], 319)  # 317 text + 2 INIT fonts
            meta, _ = load_v2_package(pkg_out)
            patched_dat_names = sorted(meta["dat_patches"].keys())

            # 2. Prepare temp copy of game dir (only patched DATs + BOF4.exe)
            tmp_game = tmp_root / "game_copy"
            tmp_dat = tmp_game / "DAT"
            tmp_dat.mkdir(parents=True)
            shutil.copy2(EXE_PATH, tmp_game / "BOF4.exe")

            orig_hashes = {"BOF4.exe": hashlib.sha256(EXE_PATH.read_bytes()).hexdigest()}
            for fname in patched_dat_names:
                src = DAT_DIR / fname
                shutil.copy2(src, tmp_dat / fname)
                orig_hashes[fname] = hashlib.sha256(src.read_bytes()).hexdigest()

            clean_init_cat = DatArchive.from_file(DAT_DIR / "INIT.DAT").find_text_entry(CATALOG_DEST).data
            clean_aread000_portrait = DatArchive.from_file(DAT_DIR / "AREAD000.DAT").entries[9].data

            # 3. Apply v2 patch to temp game copy
            apply_res = apply_v2_patch(tmp_game, pkg_path=pkg_out, create_backup=True)
            self.assertEqual(apply_res["errors"], [])
            self.assertEqual(apply_res["patched_dat_files"], len(patched_dat_names))
            self.assertEqual(apply_res["patched_dat_entries"], 319)
            self.assertTrue(apply_res["pe_checksum_valid"])
            self.assertTrue(verify_pe_checksum((tmp_game / "BOF4.exe").read_bytes()))

            # Verify INIT.DAT[7] untouched, INIT.DAT[8..9] extended to 130 glyphs, INIT[5] & SGAMENX[2] variants!
            p_init = DatArchive.from_file(tmp_dat / "INIT.DAT")
            self.assertEqual(p_init.find_text_entry(CATALOG_DEST).data, clean_init_cat)
            self.assertEqual(p_init.find_entry(TYPE_PC_FONT, FONT_16_DEST).size, 130 * 128)
            self.assertEqual(p_init.find_entry(TYPE_PC_FONT, FONT_24_DEST).size, 130 * 288)
            init5_blk = decode_text_block(p_init.find_text_entry(0x10000).data, ptbr_mode=True)
            sgx2_blk = decode_text_block(
                DatArchive.from_file(tmp_dat / "SGAMENX.DAT").find_text_entry(0x10000).data,
                ptbr_mode=True,
            )
            init5_s19 = init5_blk.slices[init5_blk.slot_to_slice[19]].text
            sgx2_s19 = sgx2_blk.slices[sgx2_blk.slot_to_slice[19]].text
            self.assertIn("{BTN_1}: Confirmar  {BTN_2}: Sair", init5_s19)
            self.assertIn("{BTN_0}: Confirmar  {BTN_1}: Sair", sgx2_s19)

            # Verify AB000_00[1] Sec0 <-> BTLEND[5] synced and 4-byte aligned
            p_ab = DatArchive.from_file(tmp_dat / "AB000_00.DAT").find_text_entry(0x00000).data
            p_be = DatArchive.from_file(tmp_dat / "BTLEND.DAT").find_text_entry(0x10000).data
            ab_s0, _ = split_multisection(p_ab, 2)
            self.assertTrue(ab_s0.startswith(p_be))
            self.assertIn(encode_ptbr_string("participar do combate."), p_be)

            # Verify AREAD000 portrait entry untouched & {PORTRAIT:C2:40} preserved byte-exact
            p_a000 = DatArchive.from_file(tmp_dat / "AREAD000.DAT")
            self.assertEqual(p_a000.entries[9].data, clean_aread000_portrait)
            self.assertIn(b"\x14\xc2@\"Ouvi dizer", p_a000.find_text_entry(0x00000).data)

            # 4. Restore backup and verify exact SHA256 match on EVERY file + BOF4.exe
            restore_res = restore_v2_backup(tmp_game, pkg_path=pkg_out)
            self.assertEqual(restore_res["errors"], [])
            self.assertTrue(restore_res["exe_clean_match"])
            self.assertEqual(restore_res["exe_restored_sha256"], CLEAN_BOF4_EXE_SHA256)
            self.assertEqual(
                hashlib.sha256((tmp_game / "BOF4.exe").read_bytes()).hexdigest(),
                orig_hashes["BOF4.exe"],
            )
            for fname in patched_dat_names:
                self.assertEqual(
                    hashlib.sha256((tmp_dat / fname).read_bytes()).hexdigest(),
                    orig_hashes[fname],
                    f"Restore SHA256 mismatch for {fname}",
                )

    def test_build_rejects_invalid_shard(self):
        """build_translation_package must abort with BuildValidationError if a locked entry is edited."""
        with tempfile.TemporaryDirectory() as td:
            tmp_root = Path(td)
            tmp_corpus = tmp_root / "corpus"
            shutil.copytree(DEFAULT_CORPUS_DIR, tmp_corpus)

            s1_path = tmp_corpus / "shard_01_menus_ui.json"
            s1 = json.loads(s1_path.read_text(encoding="utf-8"))
            for e in s1["entries"]:
                if e["locked"] and e.get("lock_reason") == "item_name_en":
                    e["ptbr"] = "Anel de Gelo"
                    break
            s1_path.write_text(json.dumps(s1, ensure_ascii=False, indent=2), encoding="utf-8")

            with self.assertRaises(BuildValidationError):
                build_translation_package(
                    corpus_dir=tmp_corpus,
                    game_dir=GAME_DIR,
                    pkg_path=tmp_root / "should_not_exist.pkg",
                    allow_empty_ptbr=True,
                )
            self.assertFalse((tmp_root / "should_not_exist.pkg").exists())


if __name__ == "__main__":
    unittest.main()
