"""Shard JSON validator and CLI for Breath of Fire IV PC native PT-BR translation.

Usage:
    python3 -m bof4_ptbr.validate <shard.json> [<shard2.json> ...]
    python3 -m bof4_ptbr.validate --allow-empty-ptbr <shard.json>

Exit code is 0 iff zero validation errors across all checked shards.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from bof4_ptbr.codec import (
    CONTEXT_BUDGETS,
    SPECIAL_TAG_TO_BYTE,
    CodecError,
    encode_ptbr_string,
    extract_tags,
    has_legacy_jp,
    load_vwf_tables,
    measure_line_px,
    split_pages_and_lines,
)

# Structural tags that must appear in the EXACT same sequence in EN and PT-BR
_ORDERED_STRUCTURAL_PREFIXES = (
    "{PORTRAIT:",
    "{GOTO:",
    "{SUBMSG:",
    "{CHOICE:",
    "{CHOICE_RAW:",
    "{WIN:",
    "{SFX:",
    "{WAIT:",
    "{SPEED:",
    "{FX:",
    "{COND:",
    "{OP19:",
)
_ORDERED_STRUCTURAL_EXACT = {
    "{/SPEED}",
    "{FX_ON}",
    "{FX_OFF}",
    "{OP18}",
}

# Variable / substitution / icon tags whose exact multiset must be preserved (order may change for PT-BR grammar)
_MULTISET_VALUE_PREFIXES = (
    "{CHAR:",
    "{VAR:",
    "{CAT:",
    "{COLOR:",
)
_MULTISET_VALUE_EXACT = {
    "{LEADER}",
    "{/COLOR}",
    "{ZENNY}",
    "{IV}",
    "{STAR}",
    "{DEG}",
    "{GT}",
    "{MDOT}",
    "{WAVE}",
    "{DOT2}",
    "{LQ}",
    "{RQ}",
    *{f"{{BTN_{i}}}" for i in range(10)},
}


@dataclass
class ValidationIssue:
    """Single structured validation error for a shard entry."""

    entry_id: str
    code: str
    message: str
    severity: str = "error"

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.entry_id} ({self.code}): {self.message}"


def _classify_tags(
    text: str,
    *,
    include_page_in_ordered: bool = True,
) -> Tuple[List[str], collections.Counter, int]:
    ordered: List[str] = []
    bag: collections.Counter = collections.Counter()
    page_count = 0
    for tag in extract_tags(text):
        if tag == "{PAGE}":
            page_count += 1
            if include_page_in_ordered:
                ordered.append(tag)
        elif tag in _ORDERED_STRUCTURAL_EXACT or tag.startswith(_ORDERED_STRUCTURAL_PREFIXES):
            ordered.append(tag)
        elif tag in _MULTISET_VALUE_EXACT or tag.startswith(_MULTISET_VALUE_PREFIXES):
            bag[tag] += 1
    return ordered, bag, page_count


def _strip_all_tags(text: str) -> str:
    """Return non-tag visible prose characters (ignoring whitespace and control tags)."""
    out = text
    for tag in set(extract_tags(text)):
        out = out.replace(tag, "")
    return out.strip()


def _check_balanced_colors(text: str) -> Optional[str]:
    depth = 0
    for tag in extract_tags(text):
        if tag.startswith("{COLOR:"):
            depth += 1
        elif tag == "{/COLOR}":
            if depth <= 0:
                return "Unmatched {/COLOR} without opening {COLOR:XX}"
            depth -= 1
    if depth != 0:
        return f"Unclosed {{COLOR:XX}} tag(s): {depth} remaining open"
    return None


def validate_entry(
    entry: Dict[str, Any],
    *,
    allow_empty_ptbr: bool = False,
    vwf_tables: Optional[Dict[str, Dict[int, Tuple[int, int]]]] = None,
) -> List[ValidationIssue]:
    """Validate a single corpus shard entry dict against all encoding, tag, and layout constraints."""
    issues: List[ValidationIssue] = []
    eid = str(entry.get("id", "<unknown>"))
    en = str(entry.get("en", ""))
    ptbr = str(entry.get("ptbr", ""))
    locked = bool(entry.get("locked", False))
    context = str(entry.get("context", "dialogue_0p"))
    allow_page_split = bool(entry.get("allow_page_split", False))
    preserve_line_count = bool(entry.get("preserve_line_count", False))
    font_slot = int(entry.get("font_slot", 1))

    # 1. Locked entries must remain untouched (empty ptbr or byte-identical to en)
    if locked:
        if ptbr != "" and ptbr != en:
            issues.append(
                ValidationIssue(
                    eid,
                    "LOCKED_MODIFIED",
                    f"Locked entry was modified (en={en!r}, ptbr={ptbr!r})",
                )
            )
        return issues

    # Skip pure-tag / empty / legacy-JP stubs that have no translatable prose
    en_visible = _strip_all_tags(en)
    if not en_visible or has_legacy_jp(en):
        if ptbr and ptbr != en:
            try:
                encode_ptbr_string(ptbr)
            except CodecError as exc:
                issues.append(ValidationIssue(eid, "INVALID_ENCODING", str(exc)))
        return issues

    # 2. Unlocked translatable entries must be non-empty (unless --allow-empty-ptbr)
    if not ptbr:
        if not allow_empty_ptbr:
            issues.append(ValidationIssue(eid, "EMPTY_TRANSLATION", "Unlocked entry has empty 'ptbr'"))
        return issues

    # 3. Strict PC PT-BR encoding check (0x20..0x7D, 0x88..0xA1, valid opcodes only)
    try:
        encode_ptbr_string(ptbr)
    except CodecError as exc:
        issues.append(ValidationIssue(eid, "INVALID_ENCODING", str(exc)))
        return issues  # Cannot safely run tag/layout analysis on malformed tag syntax

    # 4. Structural & variable tag preservation
    en_ord, en_bag, en_pages_cnt = _classify_tags(en, include_page_in_ordered=not allow_page_split)
    pt_ord, pt_bag, pt_pages_cnt = _classify_tags(ptbr, include_page_in_ordered=not allow_page_split)

    if en_ord != pt_ord:
        issues.append(
            ValidationIssue(
                eid,
                "TAG_MISMATCH",
                f"Structural tag sequence mismatch: expected {en_ord}, got {pt_ord}",
            )
        )
    if en_bag != pt_bag:
        issues.append(
            ValidationIssue(
                eid,
                "TAG_MISMATCH",
                f"Variable/icon/color tag multiset mismatch: expected {dict(en_bag)}, got {dict(pt_bag)}",
            )
        )
    # Check balanced colors only when EN itself had balanced colors
    if _check_balanced_colors(en) is None:
        color_err = _check_balanced_colors(ptbr)
        if color_err:
            issues.append(ValidationIssue(eid, "TAG_MISMATCH", color_err))

    # 5. Layout, VWF pixel width, choice-count, and lines-per-page checks
    tables = vwf_tables if vwf_tables is not None else load_vwf_tables()
    default_px, default_lines = CONTEXT_BUDGETS.get(context, (228, None))
    max_px = entry.get("max_px")
    max_px = int(max_px) if max_px is not None else default_px
    max_lines = entry.get("max_lines")
    max_lines = int(max_lines) if max_lines is not None else default_lines

    en_pages = split_pages_and_lines(en)
    pt_pages = split_pages_and_lines(ptbr)

    # Check selectable choice option counts (split ONLY on \n / 0x01, NOT {NL2} / 0x08)
    en_choice_pages = [p for p in en_pages if p["is_choice"]]
    pt_choice_pages = [p for p in pt_pages if p["is_choice"]]
    if len(en_choice_pages) != len(pt_choice_pages):
        issues.append(
            ValidationIssue(
                eid,
                "CHOICE_COUNT_MISMATCH",
                f"Choice box count mismatch: expected {len(en_choice_pages)}, got {len(pt_choice_pages)}",
            )
        )
    else:
        for c_idx, (ecp, pcp) in enumerate(zip(en_choice_pages, pt_choice_pages)):
            en_c_items = len(ecp["choice_items"])  # type: ignore[arg-type]
            pt_c_items = len(pcp["choice_items"])  # type: ignore[arg-type]
            if en_c_items != pt_c_items:
                issues.append(
                    ValidationIssue(
                        eid,
                        "CHOICE_COUNT_MISMATCH",
                        f"Choice box #{c_idx} selectable option count mismatch: expected {en_c_items}, got {pt_c_items}",
                    )
                )

    # Compute EN baseline maxes so rare vanilla outliers don't create impossible budgets
    en_max_px_non_choice = max(
        (
            measure_line_px(line, font_slot=font_slot, vwf_tables=tables)
            for p in en_pages
            if not p["is_choice"]
            for line in p["lines"]  # type: ignore[attr-defined]
        ),
        default=0,
    )
    en_max_px_choice = max(
        (
            measure_line_px(line, font_slot=font_slot, vwf_tables=tables)
            for p in en_pages
            if p["is_choice"]
            for line in p["lines"]  # type: ignore[attr-defined]
        ),
        default=0,
    )
    en_max_lines_non_choice = max(
        (len(p["lines"]) for p in en_pages if not p["is_choice"]),  # type: ignore[arg-type]
        default=0,
    )

    eff_max_px = max(max_px, en_max_px_non_choice)
    eff_choice_px = max(min(max_px, CONTEXT_BUDGETS["choice"][0]), en_max_px_choice)
    eff_max_lines = (
        max(max_lines, en_max_lines_non_choice) if max_lines is not None else None
    )

    for p_idx, page in enumerate(pt_pages):
        lines: List[str] = page["lines"]  # type: ignore[assignment]
        page_is_choice = bool(page["is_choice"])
        line_limit = eff_choice_px if page_is_choice else eff_max_px

        if not page_is_choice and eff_max_lines is not None and len(lines) > eff_max_lines:
            issues.append(
                ValidationIssue(
                    eid,
                    "PAGE_LINES_OVERFLOW",
                    f"Page {p_idx} has {len(lines)} lines (max {eff_max_lines})",
                )
            )

        for l_idx, line in enumerate(lines):
            px = measure_line_px(line, font_slot=font_slot, vwf_tables=tables)
            if px > line_limit:
                issues.append(
                    ValidationIssue(
                        eid,
                        "LINE_WIDTH_OVERFLOW",
                        f"Page {p_idx} line {l_idx} is {px}px > max {line_limit}px: {line!r}",
                    )
                )

    if preserve_line_count and len(en_pages) == len(pt_pages):
        for p_idx, (ep, pp) in enumerate(zip(en_pages, pt_pages)):
            e_n = len(ep["lines"])  # type: ignore[arg-type]
            p_n = len(pp["lines"])  # type: ignore[arg-type]
            if e_n != p_n:
                issues.append(
                    ValidationIssue(
                        eid,
                        "LINE_COUNT_MISMATCH",
                        f"Page {p_idx} must preserve exact line count ({e_n}), got {p_n}",
                    )
                )

    return issues


def validate_shard(
    shard: Dict[str, Any] | str | Path,
    *,
    allow_empty_ptbr: bool = False,
    vwf_tables: Optional[Dict[str, Dict[int, Tuple[int, int]]]] = None,
) -> List[ValidationIssue]:
    """Validate an entire corpus shard (loaded dict or path to JSON file)."""
    if isinstance(shard, (str, Path)):
        shard_path = Path(shard)
        data = json.loads(shard_path.read_text(encoding="utf-8"))
    else:
        data = shard

    entries = data.get("entries")
    if not isinstance(entries, list):
        return [ValidationIssue("<shard>", "INVALID_SCHEMA", "Shard JSON missing 'entries' list")]

    tables = vwf_tables if vwf_tables is not None else load_vwf_tables()
    seen_ids: set[str] = set()
    issues: List[ValidationIssue] = []

    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            issues.append(ValidationIssue(f"index:{idx}", "INVALID_SCHEMA", "Entry is not a JSON object"))
            continue
        eid = str(entry.get("id", f"index:{idx}"))
        if eid in seen_ids:
            issues.append(ValidationIssue(eid, "DUPLICATE_ID", f"Duplicate entry id {eid!r} in shard"))
        seen_ids.add(eid)
        issues.extend(validate_entry(entry, allow_empty_ptbr=allow_empty_ptbr, vwf_tables=tables))

    return issues


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Breath of Fire IV PT-BR translation corpus shard JSON file(s)."
    )
    parser.add_argument("shards", nargs="+", type=Path, help="Path(s) to shard JSON file(s)")
    parser.add_argument(
        "--allow-empty-ptbr",
        action="store_true",
        help="Allow empty 'ptbr' fields (for validating freshly extracted untranslated shards)",
    )
    parser.add_argument(
        "--max-errors",
        type=int,
        default=50,
        help="Maximum error lines to print per shard (default: 50)",
    )
    args = parser.parse_args(argv)

    tables = load_vwf_tables()
    total_errors = 0

    for shard_path in args.shards:
        issues = validate_shard(
            shard_path,
            allow_empty_ptbr=args.allow_empty_ptbr,
            vwf_tables=tables,
        )
        total_errors += len(issues)
        status = "OK" if not issues else f"FAIL ({len(issues)} errors)"
        print(f"{shard_path}: {status}")
        for issue in issues[: args.max_errors]:
            print(f"  {issue}")
        if len(issues) > args.max_errors:
            print(f"  ... ({len(issues) - args.max_errors} more errors omitted)")

    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
