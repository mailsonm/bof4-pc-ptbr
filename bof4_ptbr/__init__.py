"""Breath of Fire IV PC native PT-BR translation toolkit."""

from bof4_ptbr.codec import (
    BYTE_TO_PTBR_CHAR,
    CONTEXT_BUDGETS,
    DEFAULT_DAT_DIR,
    DEFAULT_EXE_PATH,
    DEFAULT_GAME_DIR,
    OPCODE_ARG_LEN,
    PTBR_CHAR_TO_BYTE,
    PTBR_CHARS,
    CodecError,
    TextBlock,
    TextSection,
    TextSlice,
    count_portraits,
    decode_bytes,
    decode_slice,
    decode_text_block,
    encode_bytes,
    encode_ptbr_string,
    encode_slice,
    encode_text_block,
    extract_tags,
    has_legacy_jp,
    load_vwf_tables,
    measure_line_px,
    split_pages_and_lines,
    wrap_dialogue_text,
)


def __getattr__(name: str):
    """Lazy-load validate symbols so `python3 -m bof4_ptbr.validate` emits no RuntimeWarning."""
    if name in ("ValidationIssue", "validate_entry", "validate_shard"):
        from bof4_ptbr import validate

        return getattr(validate, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "BYTE_TO_PTBR_CHAR",
    "CONTEXT_BUDGETS",
    "CodecError",
    "DEFAULT_DAT_DIR",
    "DEFAULT_EXE_PATH",
    "DEFAULT_GAME_DIR",
    "OPCODE_ARG_LEN",
    "PTBR_CHAR_TO_BYTE",
    "PTBR_CHARS",
    "TextBlock",
    "TextSection",
    "TextSlice",
    "ValidationIssue",
    "count_portraits",
    "decode_bytes",
    "decode_slice",
    "decode_text_block",
    "encode_bytes",
    "encode_ptbr_string",
    "encode_slice",
    "encode_text_block",
    "extract_tags",
    "has_legacy_jp",
    "load_vwf_tables",
    "measure_line_px",
    "split_pages_and_lines",
    "validate_entry",
    "validate_shard",
    "wrap_dialogue_text",
]
