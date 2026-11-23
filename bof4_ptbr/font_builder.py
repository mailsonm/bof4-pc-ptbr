"""Breath of Fire IV (PC) 4bpp Font Synthesizer & INIT.DAT Font Patcher.

Synthesizes 26 native Portuguese (PT-BR) accented and ordinal glyphs at single-byte
codes 0x88..0xA1 (glyph IDs 104..129) for both the 16x16 UI font (INIT.DAT[8],
slot 0) and the 24x24 main dialogue/menu font (INIT.DAT[9], slot 1), using Capcom's
original 4bpp nibble ramp (0=transparent, 1=bright core .. 8=outer anti-alias)
and VWF metric rules (left_bearing = max(0, x0 - 1), advance_width = width + 2).
"""

from __future__ import annotations

import math
import os
import struct
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

# Shared encoding contract across codec, font_builder, and exe_patcher.
PTBR_START_CODE: int = 0x88
PTBR_CHARS: list[str] = [
    "á", "à", "â", "ã", "é", "ê", "í", "ó", "ô", "õ", "ú", "ç",
    "Á", "À", "Â", "Ã", "É", "Ê", "Í", "Ó", "Ô", "Õ", "Ú", "Ç",
    "º", "ª",
]  # 0x88 .. 0xA1 (26 chars -> glyph IDs 104 .. 129)

CHAR_TO_BYTE: dict[str, int] = {
    ch: PTBR_START_CODE + idx for idx, ch in enumerate(PTBR_CHARS)
}
BYTE_TO_CHAR: dict[int, str] = {v: k for k, v in CHAR_TO_BYTE.items()}

VANILLA_GLYPH_COUNT: int = 104  # 0x20 .. 0x87
TOTAL_GLYPH_COUNT: int = VANILLA_GLYPH_COUNT + len(PTBR_CHARS)  # 130

FONT16_ENTRY_TYPE: int = 0x00000005
FONT16_ENTRY_DEST: int = 0x00001000
FONT24_ENTRY_TYPE: int = 0x00000005
FONT24_ENTRY_DEST: int = 0x00001801

DEFAULT_GAME_DIR = Path(
    "/home/mailson/Games/breath-of-fire-iv/drive_c/GOG Games/Breath of Fire IV"
)

# Glyph recipes: (base_ascii, accent_kind)
_RECIPES: list[tuple[str, str]] = [
    ("a", "acute_lo"),
    ("a", "grave_lo"),
    ("a", "circ_lo"),
    ("a", "tilde_lo"),
    ("e", "acute_lo"),
    ("e", "circ_lo"),
    ("i", "acute_i"),
    ("o", "acute_lo"),
    ("o", "circ_lo"),
    ("o", "tilde_lo"),
    ("u", "acute_lo"),
    ("c", "cedilla_lo"),
    ("A", "acute_hi"),
    ("A", "grave_hi"),
    ("A", "circ_hi"),
    ("A", "tilde_hi"),
    ("E", "acute_hi"),
    ("E", "circ_hi"),
    ("I", "acute_hi"),
    ("O", "acute_hi"),
    ("O", "circ_hi"),
    ("O", "tilde_hi"),
    ("U", "acute_hi"),
    ("C", "cedilla_hi"),
    ("o", "ord_o"),
    ("a", "ord_a"),
]


# ---------------------------------------------------------------------------
# Low-level 4bpp nibble <-> float intensity helpers
# ---------------------------------------------------------------------------

def nibble_to_alpha(n: int) -> float:
    """Convert Capcom 4bpp nibble (0=transparent, 1=100% .. 8=12.5%) to [0, 1]."""
    if n <= 0:
        return 0.0
    if n >= 8:
        return 1.0 / 8.0
    return (9 - n) / 8.0


def alpha_to_nibble(a: float) -> int:
    """Convert normalized opacity [0, 1] back to Capcom 4bpp nibble (0..8)."""
    if a < 0.0625:
        return 0
    # Map [0.0625 .. 1.0] -> 8 .. 1
    level = int(round(a * 8.0))
    level = max(1, min(8, level))
    return 9 - level


def decode_glyph_4bpp(font_bytes: bytes, glyph_id: int, dim: int) -> list[list[int]]:
    """Decode a single dim x dim 4bpp glyph into a 2D list of nibbles (0..8)."""
    bpg = (dim * dim) // 2
    offset = glyph_id * bpg
    chunk = font_bytes[offset : offset + bpg]
    grid: list[list[int]] = []
    for y in range(dim):
        row: list[int] = []
        row_base = (y * dim) // 2
        for x in range(0, dim, 2):
            byte = chunk[row_base + (x // 2)]
            row.append(byte & 0x0F)
            row.append((byte >> 4) & 0x0F)
        grid.append(row)
    return grid


def encode_glyph_4bpp(grid: list[list[int]], dim: int) -> bytes:
    """Encode a dim x dim 2D nibble grid (0..8) into Capcom's 4bpp format."""
    out = bytearray((dim * dim) // 2)
    idx = 0
    for y in range(dim):
        row = grid[y]
        for x in range(0, dim, 2):
            lo = max(0, min(8, int(row[x])))
            hi = max(0, min(8, int(row[x + 1])))
            out[idx] = lo | (hi << 4)
            idx += 1
    return bytes(out)


def _grid_to_alpha(grid: list[list[int]]) -> list[list[float]]:
    return [[nibble_to_alpha(v) for v in row] for row in grid]


def _alpha_to_grid(alpha: list[list[float]]) -> list[list[int]]:
    return [[alpha_to_nibble(v) for v in row] for row in alpha]


def glyph_bbox(grid: list[list[int]]) -> tuple[int, int, int, int] | None:
    """Return (x0, y0, x1, y1) inclusive bounding box of non-zero nibbles."""
    x0, y0 = 999, 999
    x1, y1 = -1, -1
    for y, row in enumerate(grid):
        for x, v in enumerate(row):
            if v > 0:
                if x < x0:
                    x0 = x
                if x > x1:
                    x1 = x
                if y < y0:
                    y0 = y
                if y > y1:
                    y1 = y
    if x1 < 0:
        return None
    return (x0, y0, x1, y1)


def compute_vwf_metric(grid: list[list[int]], dim: int) -> tuple[int, int]:
    """Compute Capcom's exact (left_bearing, advance_width) from glyph pixels.

    Across all 52 vanilla A-Z / a-z letters in both 16x16 and 24x24:
        left_bearing  = max(0, x0 - 1)
        advance_width = min(dim, (x1 - x0 + 1) + 2)
    """
    bb = glyph_bbox(grid)
    if bb is None:
        return (0, dim // 3)
    x0, _, x1, _ = bb
    lb = max(0, x0 - 1)
    adv = min(dim, (x1 - x0 + 1) + 2)
    return (lb, adv)


# ---------------------------------------------------------------------------
# Analytical supersampled vector drawing helpers for crisp serif diacritics
# ---------------------------------------------------------------------------

def _dist_point_to_segment(
    px: float, py: float, x0: float, y0: float, x1: float, y1: float
) -> tuple[float, float]:
    """Return (euclidean_distance, t in [0,1]) from (px,py) to segment."""
    dx = x1 - x0
    dy = y1 - y0
    l2 = dx * dx + dy * dy
    if l2 <= 1e-9:
        return (math.hypot(px - x0, py - y0), 0.0)
    t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / l2))
    proj_x = x0 + t * dx
    proj_y = y0 + t * dy
    return (math.hypot(px - proj_x, py - proj_y), t)


def _rasterize_supersampled(
    dim: int,
    inside_fn: Callable[[float, float], bool],
    samples: int = 8,
) -> list[list[float]]:
    """Evaluate boolean shape indicator with samples x samples supersampling."""
    out = [[0.0] * dim for _ in range(dim)]
    inv = 1.0 / samples
    half = 0.5 * inv
    inv_total = 1.0 / (samples * samples)
    for y in range(dim):
        for x in range(dim):
            hits = 0
            for sy in range(samples):
                py = y + half + sy * inv
                for sx in range(samples):
                    px = x + half + sx * inv
                    if inside_fn(px, py):
                        hits += 1
            if hits:
                out[y][x] = hits * inv_total
    return out


def _tapered_stroke_fn(
    x0: float, y0: float, r0: float, x1: float, y1: float, r1: float
) -> Callable[[float, float], bool]:
    def fn(px: float, py: float) -> bool:
        d, t = _dist_point_to_segment(px, py, x0, y0, x1, y1)
        r = r0 + (r1 - r0) * t
        return d <= r
    return fn


def _polyline_stroke_fn(
    pts: list[tuple[float, float, float]]
) -> Callable[[float, float], bool]:
    """Polyline of (x, y, radius) control points with smooth linear taper."""
    segs = list(zip(pts[:-1], pts[1:]))

    def fn(px: float, py: float) -> bool:
        for (x0, y0, r0), (x1, y1, r1) in segs:
            d, t = _dist_point_to_segment(px, py, x0, y0, x1, y1)
            if d <= r0 + (r1 - r0) * t:
                return True
        return False

    return fn


def _composite_max(
    base: list[list[float]], overlay: list[list[float]]
) -> list[list[float]]:
    dim = len(base)
    return [
        [max(base[y][x], overlay[y][x]) for x in range(dim)]
        for y in range(dim)
    ]


def _resample_vertical_region(
    alpha: list[list[float]],
    src_y0: float,
    src_y1: float,
    dst_y0: float,
    dst_y1: float,
    contrast_boost: float = 1.12,
) -> list[list[float]]:
    """Smoothly compress a glyph vertically into [dst_y0, dst_y1] keeping baseline crisp."""
    dim = len(alpha)
    out = [[0.0] * dim for _ in range(dim)]
    src_span = src_y1 - src_y0
    dst_span = dst_y1 - dst_y0
    if dst_span <= 0.0:
        return out

    # Oversample 4 vertical subsamples per output pixel for clean box/linear filter
    sub = 4
    for dy in range(dim):
        for dx in range(dim):
            acc = 0.0
            for s in range(sub):
                py = dy + (s + 0.5) / sub
                if py < dst_y0 - 0.5 or py > dst_y1 + 0.5:
                    continue
                sy = src_y0 + (py - dst_y0) * (src_span / dst_span)
                if sy < 0.0 or sy > dim - 1.0:
                    continue
                iy = int(math.floor(sy))
                fy = sy - iy
                iy1 = min(dim - 1, iy + 1)
                val = alpha[iy][dx] * (1.0 - fy) + alpha[iy1][dx] * fy
                acc += val
            avg = acc / sub
            if avg > 0.02:
                # Preserve white core crispness after slight vertical compression
                avg = min(1.0, avg * contrast_boost)
                out[dy][dx] = avg
    return out


def _resample_box_to_rect(
    alpha: list[list[float]],
    src_box: tuple[int, int, int, int],
    dst_rect: tuple[float, float, float, float],
    contrast_boost: float = 1.25,
) -> list[list[float]]:
    """Resample a cropped glyph alpha region into a destination rectangle."""
    dim = len(alpha)
    sx0, sy0, sx1, sy1 = src_box
    dx0, dy0, dx1, dy1 = dst_rect
    sw = float(sx1 - sx0 + 1)
    sh = float(sy1 - sy0 + 1)
    dw = dx1 - dx0
    dh = dy1 - dy0
    out = [[0.0] * dim for _ in range(dim)]
    sub = 4
    inv_sub2 = 1.0 / (sub * sub)

    for y in range(dim):
        for x in range(dim):
            acc = 0.0
            for sy in range(sub):
                py = y + (sy + 0.5) / sub
                if py < dy0 or py > dy1:
                    continue
                fy_src = sy0 + ((py - dy0) / dh) * (sh - 1.0)
                iy0 = max(0, min(dim - 1, int(math.floor(fy_src))))
                iy1 = min(dim - 1, iy0 + 1)
                wy = fy_src - iy0
                for sx in range(sub):
                    px = x + (sx + 0.5) / sub
                    if px < dx0 or px > dx1:
                        continue
                    fx_src = sx0 + ((px - dx0) / dw) * (sw - 1.0)
                    ix0 = max(0, min(dim - 1, int(math.floor(fx_src))))
                    ix1 = min(dim - 1, ix0 + 1)
                    wx = fx_src - ix0
                    v00 = alpha[iy0][ix0]
                    v10 = alpha[iy0][ix1]
                    v01 = alpha[iy1][ix0]
                    v11 = alpha[iy1][ix1]
                    v = (
                        v00 * (1.0 - wx) * (1.0 - wy)
                        + v10 * wx * (1.0 - wy)
                        + v01 * (1.0 - wx) * wy
                        + v11 * wx * wy
                    )
                    acc += v
            val = acc * inv_sub2
            if val > 0.03:
                out[y][x] = min(1.0, val * contrast_boost)
    return out


# ---------------------------------------------------------------------------
# Diacritic shapes for 24x24 and 16x16
# ---------------------------------------------------------------------------

def _optical_center_x(base_ch: str, base_grid: list[list[int]], dim: int) -> float:
    """Optical horizontal center of a base letter's top cap/x-height region."""
    bb = glyph_bbox(base_grid)
    if bb is None:
        return dim * 0.5
    x0, _, x1, _ = bb
    cx = (x0 + x1 + 1.0) * 0.5
    # Fine optical nudges matching Capcom's serif proportions
    if dim == 24:
        nudges = {
            "a": 0.3,
            "e": 0.1,
            "i": 0.4,
            "o": 0.0,
            "u": 0.2,
            "c": 0.2,
            "A": -0.1,
            "E": -0.4,
            "I": 0.0,
            "O": 0.0,
            "U": 0.0,
            "C": 0.2,
        }
    else:
        nudges = {
            "a": 0.2,
            "e": 0.0,
            "i": 0.3,
            "o": 0.0,
            "u": 0.2,
            "c": 0.2,
            "A": -0.1,
            "E": -0.3,
            "I": 0.0,
            "O": 0.0,
            "U": 0.0,
            "C": 0.2,
        }
    return cx + nudges.get(base_ch, 0.0)


def _draw_accent_24(kind: str, cx: float) -> list[list[float]]:
    if kind in ("acute_lo", "acute_i"):
        # Crisp serif acute wedge sitting in y=3.0..7.4
        dx_l = 1.6 if kind == "acute_i" else 1.8
        dx_r = 2.0 if kind == "acute_i" else 2.5
        fn = _tapered_stroke_fn(
            cx + dx_r, 3.3, 1.05, cx - dx_l, 7.1, 0.52
        )
        return _rasterize_supersampled(24, fn)

    if kind == "grave_lo":
        fn = _tapered_stroke_fn(
            cx - 2.4, 3.3, 1.05, cx + 1.9, 7.1, 0.52
        )
        return _rasterize_supersampled(24, fn)

    if kind == "circ_lo":
        pts = [
            (cx - 3.6, 7.2, 0.65),
            (cx, 3.4, 1.02),
            (cx + 3.6, 7.2, 0.65),
        ]
        return _rasterize_supersampled(24, _polyline_stroke_fn(pts))

    if kind == "tilde_lo":
        # Classic serif S-wave tilde in y=3.6..7.0
        pts = [
            (cx - 4.2, 6.4, 0.55),
            (cx - 2.3, 4.4, 0.90),
            (cx, 5.4, 0.95),
            (cx + 2.3, 6.4, 0.90),
            (cx + 4.2, 4.4, 0.55),
        ]
        return _rasterize_supersampled(24, _polyline_stroke_fn(pts))

    if kind == "acute_hi":
        # Uppercase acute sitting cleanly in y=0.4..3.9 above cap (y=5.4..20)
        fn = _tapered_stroke_fn(
            cx + 2.5, 0.8, 0.92, cx - 1.7, 3.8, 0.48
        )
        return _rasterize_supersampled(24, fn)

    if kind == "grave_hi":
        fn = _tapered_stroke_fn(
            cx - 2.5, 0.8, 0.92, cx + 1.7, 3.8, 0.48
        )
        return _rasterize_supersampled(24, fn)

    if kind == "circ_hi":
        pts = [
            (cx - 3.6, 3.9, 0.58),
            (cx, 0.8, 0.92),
            (cx + 3.6, 3.9, 0.58),
        ]
        return _rasterize_supersampled(24, _polyline_stroke_fn(pts))

    if kind == "tilde_hi":
        pts = [
            (cx - 4.2, 3.4, 0.50),
            (cx - 2.1, 1.5, 0.82),
            (cx, 2.4, 0.86),
            (cx + 2.1, 3.3, 0.82),
            (cx + 4.2, 1.5, 0.50),
        ]
        return _rasterize_supersampled(24, _polyline_stroke_fn(pts))

    if kind in ("cedilla_lo", "cedilla_hi"):
        # Smooth serif cedilla hook attached at bottom of c/C (y=19.2..23.2)
        cx_c = cx + (0.0 if kind == "cedilla_lo" else 0.1)
        pts = [
            (cx_c, 19.3, 0.72),
            (cx_c - 0.5, 20.8, 0.72),
            (cx_c + 1.2, 21.1, 0.78),
            (cx_c + 1.5, 22.3, 0.82),
            (cx_c + 0.1, 23.0, 0.78),
            (cx_c - 1.7, 22.7, 0.55),
        ]
        return _rasterize_supersampled(24, _polyline_stroke_fn(pts))

    raise ValueError(f"Unsupported 24px accent kind: {kind}")


def _draw_accent_16(kind: str, cx: float) -> list[list[float]]:
    if kind in ("acute_lo", "acute_i"):
        dx_l = 1.0 if kind == "acute_i" else 1.2
        dx_r = 1.4 if kind == "acute_i" else 1.7
        fn = _tapered_stroke_fn(
            cx + dx_r, 1.3, 0.78, cx - dx_l, 4.1, 0.45
        )
        return _rasterize_supersampled(16, fn)

    if kind == "grave_lo":
        fn = _tapered_stroke_fn(
            cx - 1.7, 1.3, 0.78, cx + 1.2, 4.1, 0.45
        )
        return _rasterize_supersampled(16, fn)

    if kind == "circ_lo":
        pts = [
            (cx - 2.6, 4.2, 0.52),
            (cx, 1.4, 0.78),
            (cx + 2.6, 4.2, 0.52),
        ]
        return _rasterize_supersampled(16, _polyline_stroke_fn(pts))

    if kind == "tilde_lo":
        pts = [
            (cx - 3.0, 3.8, 0.45),
            (cx - 1.5, 2.1, 0.68),
            (cx, 2.9, 0.72),
            (cx + 1.5, 3.7, 0.68),
            (cx + 3.0, 2.0, 0.45),
        ]
        return _rasterize_supersampled(16, _polyline_stroke_fn(pts))

    if kind == "acute_hi":
        fn = _tapered_stroke_fn(
            cx + 1.6, 0.5, 0.65, cx - 1.1, 2.7, 0.38
        )
        return _rasterize_supersampled(16, fn)

    if kind == "grave_hi":
        fn = _tapered_stroke_fn(
            cx - 1.6, 0.5, 0.65, cx + 1.1, 2.7, 0.38
        )
        return _rasterize_supersampled(16, fn)

    if kind == "circ_hi":
        pts = [
            (cx - 2.5, 2.8, 0.44),
            (cx, 0.5, 0.66),
            (cx + 2.5, 2.8, 0.44),
        ]
        return _rasterize_supersampled(16, _polyline_stroke_fn(pts))

    if kind == "tilde_hi":
        pts = [
            (cx - 2.9, 2.6, 0.38),
            (cx - 1.4, 1.0, 0.58),
            (cx, 1.8, 0.62),
            (cx + 1.4, 2.5, 0.58),
            (cx + 2.9, 0.9, 0.38),
        ]
        return _rasterize_supersampled(16, _polyline_stroke_fn(pts))

    if kind in ("cedilla_lo", "cedilla_hi"):
        pts = [
            (cx, 12.6, 0.56),
            (cx - 0.3, 13.7, 0.56),
            (cx + 0.9, 13.9, 0.62),
            (cx + 1.0, 14.8, 0.62),
            (cx - 0.1, 15.2, 0.58),
            (cx - 1.2, 15.0, 0.44),
        ]
        return _rasterize_supersampled(16, _polyline_stroke_fn(pts))

    raise ValueError(f"Unsupported 16px accent kind: {kind}")


def _build_ordinal_glyph(
    base_grid: list[list[int]], kind: str, dim: int
) -> list[list[int]]:
    """Build crisp superscript ordinal º or ª with traditional Portuguese underline."""
    base_alpha = _grid_to_alpha(base_grid)
    bb = glyph_bbox(base_grid)
    assert bb is not None
    if dim == 24:
        # Miniature letter in top-center + crisp underline bar below it
        dst = (7.5, 3.2, 15.5, 11.4) if kind == "ord_o" else (7.0, 3.2, 16.0, 11.4)
        mini = _resample_box_to_rect(base_alpha, bb, dst, contrast_boost=1.22)
        bar = _rasterize_supersampled(
            24, _tapered_stroke_fn(8.0, 13.2, 0.60, 15.2, 13.2, 0.60)
        )
        return _alpha_to_grid(_composite_max(mini, bar))
    else:
        dst = (4.2, 1.6, 10.8, 8.2) if kind == "ord_o" else (3.8, 1.5, 11.2, 8.2)
        mini = _resample_box_to_rect(base_alpha, bb, dst, contrast_boost=1.15)
        bar = _rasterize_supersampled(
            16, _tapered_stroke_fn(4.6, 9.7, 0.45, 10.4, 9.7, 0.45)
        )
        return _alpha_to_grid(_composite_max(mini, bar))


def synthesize_single_glyph(
    font_bytes: bytes, base_ch: str, kind: str, dim: int
) -> list[list[int]]:
    """Synthesize one PT-BR dim x dim glyph from a vanilla Capcom base letter."""
    base_gid = ord(base_ch) - 0x20
    base_grid = decode_glyph_4bpp(font_bytes, base_gid, dim)

    if kind in ("ord_o", "ord_a"):
        return _build_ordinal_glyph(base_grid, kind, dim)

    base_alpha = _grid_to_alpha(base_grid)
    cx = _optical_center_x(base_ch, base_grid, dim)

    if kind == "acute_i":
        # Strip the vanilla dot above the stem of 'i'
        cut_row = 8 if dim == 24 else 5
        for y in range(cut_row + 1):
            for x in range(dim):
                base_alpha[y][x] = 0.0
    elif kind.endswith("_hi") and not kind.startswith("cedilla"):
        # Gently compress uppercase cap height so diacritics sit cleanly above
        # without clipping at y=0 or touching the capital letter's top serif.
        bb = glyph_bbox(base_grid)
        assert bb is not None
        _, y0, _, y1 = bb
        if dim == 24:
            base_alpha = _resample_vertical_region(
                base_alpha,
                src_y0=float(y0),
                src_y1=float(y1) + 0.5,
                dst_y0=5.4,
                dst_y1=float(y1) + 0.5,
                contrast_boost=1.18,
            )
        else:
            base_alpha = _resample_vertical_region(
                base_alpha,
                src_y0=float(y0),
                src_y1=float(y1) + 0.5,
                dst_y0=3.7,
                dst_y1=float(y1) + 0.5,
                contrast_boost=1.20,
            )

    accent_alpha = (
        _draw_accent_24(kind, cx) if dim == 24 else _draw_accent_16(kind, cx)
    )
    combined = _composite_max(base_alpha, accent_alpha)
    return _alpha_to_grid(combined)


def synthesize_ptbr_glyphs(
    font_bytes: bytes, dim: int
) -> tuple[bytes, dict[int, tuple[int, int]]]:
    """Append all 26 PT-BR glyphs (0x88..0xA1) to a vanilla Capcom 4bpp font blob.

    Returns (extended_font_bytes, vwf_metrics_by_byte).
    Vanilla glyphs 0x20..0x87 are preserved byte-for-byte.
    """
    bpg = (dim * dim) // 2
    expected_vanilla_size = VANILLA_GLYPH_COUNT * bpg
    if len(font_bytes) != expected_vanilla_size:
        raise ValueError(
            f"Expected vanilla {dim}x{dim} font of {expected_vanilla_size} bytes "
            f"({VANILLA_GLYPH_COUNT} glyphs), got {len(font_bytes)} bytes"
        )

    appended = bytearray(font_bytes)
    vwf: dict[int, tuple[int, int]] = {}

    for idx, (base_ch, kind) in enumerate(_RECIPES):
        code = PTBR_START_CODE + idx
        grid = synthesize_single_glyph(font_bytes, base_ch, kind, dim)
        appended.extend(encode_glyph_4bpp(grid, dim))
        vwf[code] = compute_vwf_metric(grid, dim)

    return (bytes(appended), vwf)


# ---------------------------------------------------------------------------
# INIT.DAT 1-byte-packed parser/writer (strictly matched by (type_param, dest))
# ---------------------------------------------------------------------------

def _parse_dat_entries(dat_bytes: bytes) -> list[tuple[int, int, bytes]]:
    """Parse PC .DAT container into [(type_param, dest, payload), ...]."""
    if len(dat_bytes) < 16:
        raise ValueError("DAT file too small")
    first_off = struct.unpack_from("<I", dat_bytes, 0)[0]
    if first_off == 0 or first_off % 16 != 0 or first_off > len(dat_bytes):
        raise ValueError(f"Invalid DAT TOC size: {first_off}")
    count = first_off // 16
    entries: list[tuple[int, int, bytes]] = []
    for i in range(count):
        off, sz, type_param, dest = struct.unpack_from("<4I", dat_bytes, i * 16)
        if off + sz > len(dat_bytes):
            raise ValueError(f"DAT entry {i} exceeds file length")
        entries.append((type_param, dest, dat_bytes[off : off + sz]))
    return entries


def _pack_dat_entries(entries: list[tuple[int, int, bytes]]) -> bytes:
    """Repack entries into a 1-byte-packed PC .DAT container (0 gaps, 0 pad)."""
    toc_size = len(entries) * 16
    toc = bytearray(toc_size)
    body = bytearray()
    cur_off = toc_size
    for i, (type_param, dest, payload) in enumerate(entries):
        struct.pack_into("<4I", toc, i * 16, cur_off, len(payload), type_param, dest)
        body.extend(payload)
        cur_off += len(payload)
    return bytes(toc) + bytes(body)


def extract_init_fonts(init_dat_bytes: bytes) -> tuple[bytes, bytes]:
    """Extract (font16_bytes, font24_bytes) from INIT.DAT by strict (type, dest)."""
    entries = _parse_dat_entries(init_dat_bytes)
    font16: bytes | None = None
    font24: bytes | None = None
    for type_param, dest, payload in entries:
        if type_param == FONT16_ENTRY_TYPE and dest == FONT16_ENTRY_DEST:
            font16 = payload
        elif type_param == FONT24_ENTRY_TYPE and dest == FONT24_ENTRY_DEST:
            font24 = payload
    if font16 is None or font24 is None:
        raise ValueError("INIT.DAT is missing expected Type 5 font entries (0x1000 / 0x1801)")
    return (font16, font24)


def patch_init_fonts(init_dat_bytes: bytes) -> bytes:
    """Patch INIT.DAT entries [8] (16x16) and [9] (24x24) with all 26 PT-BR glyphs.

    Preserves entry ordering, all non-font entries, all vanilla 0x20..0x87 glyphs,
    and exact 1-byte-packed DAT alignment (0 gaps, 0 trailing padding).
    """
    entries = _parse_dat_entries(init_dat_bytes)
    patched_entries: list[tuple[int, int, bytes]] = []
    found_16 = False
    found_24 = False

    for type_param, dest, payload in entries:
        if type_param == FONT16_ENTRY_TYPE and dest == FONT16_ENTRY_DEST:
            ext16, _ = synthesize_ptbr_glyphs(payload, 16)
            patched_entries.append((type_param, dest, ext16))
            found_16 = True
        elif type_param == FONT24_ENTRY_TYPE and dest == FONT24_ENTRY_DEST:
            ext24, _ = synthesize_ptbr_glyphs(payload, 24)
            patched_entries.append((type_param, dest, ext24))
            found_24 = True
        else:
            patched_entries.append((type_param, dest, payload))

    if not (found_16 and found_24):
        raise ValueError("INIT.DAT did not contain both 16x16 and 24x24 font entries")

    return _pack_dat_entries(patched_entries)


# ---------------------------------------------------------------------------
# Precomputed / cached PT-BR VWF metrics (verified from clean INIT.DAT)
# ---------------------------------------------------------------------------

def compute_ptbr_vwf_metrics_from_init(
    init_dat_bytes: bytes,
) -> tuple[dict[int, tuple[int, int]], dict[int, tuple[int, int]]]:
    """Compute (PTBR_VWF_24, PTBR_VWF_16) directly from clean INIT.DAT bytes."""
    font16, font24 = extract_init_fonts(init_dat_bytes)
    _, vwf16 = synthesize_ptbr_glyphs(font16, 16)
    _, vwf24 = synthesize_ptbr_glyphs(font24, 24)
    return (vwf24, vwf16)


def _load_default_vwf_metrics() -> tuple[dict[int, tuple[int, int]], dict[int, tuple[int, int]]]:
    init_path = DEFAULT_GAME_DIR / "DAT" / "INIT.DAT"
    if init_path.is_file():
        return compute_ptbr_vwf_metrics_from_init(init_path.read_bytes())
    # Fallback metrics if run in an environment without the game directory mounted
    return (
        {
            0x88: (5, 14), 0x89: (5, 14), 0x8A: (5, 14), 0x8B: (5, 14),
            0x8C: (6, 12), 0x8D: (6, 12), 0x8E: (8, 9),  0x8F: (6, 12),
            0x90: (6, 12), 0x91: (6, 12), 0x92: (5, 14), 0x93: (6, 12),
            0x94: (3, 19), 0x95: (3, 19), 0x96: (3, 19), 0x97: (3, 19),
            0x98: (4, 16), 0x99: (4, 16), 0x9A: (7, 10), 0x9B: (3, 18),
            0x9C: (3, 18), 0x9D: (3, 18), 0x9E: (3, 18), 0x9F: (4, 16),
            0xA0: (6, 11), 0xA1: (6, 11),
        },
        {
            0x88: (3, 10), 0x89: (3, 10), 0x8A: (3, 10), 0x8B: (3, 10),
            0x8C: (4, 9),  0x8D: (4, 9),  0x8E: (5, 7),  0x8F: (3, 10),
            0x90: (3, 10), 0x91: (3, 10), 0x92: (3, 10), 0x93: (3, 10),
            0x94: (1, 14), 0x95: (1, 14), 0x96: (1, 14), 0x97: (1, 14),
            0x98: (2, 12), 0x99: (2, 12), 0x9A: (4, 8),  0x9B: (2, 12),
            0x9C: (2, 12), 0x9D: (2, 12), 0x9E: (1, 13), 0x9F: (2, 12),
            0xA0: (3, 9),  0xA1: (2, 11),
        },
    )


PTBR_VWF_24: dict[int, tuple[int, int]]
PTBR_VWF_16: dict[int, tuple[int, int]]
PTBR_VWF_24, PTBR_VWF_16 = _load_default_vwf_metrics()


def get_ptbr_vwf_metrics() -> dict[str, dict[int, tuple[int, int]]]:
    """Return PT-BR VWF metric dicts keyed by byte (0x88..0xA1) -> (lb, adv).

    Keys:
      - ``"vwf_24"``: 24x24 main font (INIT.DAT[9])
      - ``"vwf_16"``: 16x16 UI font (INIT.DAT[8])
      - ``"vwf_dlg"``: dialogue stepper VWF (identical to vwf_24)
    """
    return {
        "vwf_24": dict(PTBR_VWF_24),
        "vwf_16": dict(PTBR_VWF_16),
        "vwf_dlg": dict(PTBR_VWF_24),
    }


# ---------------------------------------------------------------------------
# Visual QA PNG Rendering
# ---------------------------------------------------------------------------

def _blit_glyph_rgb(
    img: Image.Image,
    grid: list[list[int]],
    dst_x: int,
    dst_y: int,
    bg_rgb: tuple[int, int, int] = (16, 26, 56),
    fg_rgb: tuple[int, int, int] = (255, 255, 255),
) -> None:
    """Alpha-blend a 4bpp Capcom glyph onto an RGB image."""
    px = img.load()
    w, h = img.size
    dim = len(grid)
    for y in range(dim):
        py = dst_y + y
        if py < 0 or py >= h:
            continue
        row = grid[y]
        for x in range(dim):
            n = row[x]
            if n == 0:
                continue
            px_x = dst_x + x
            if px_x < 0 or px_x >= w:
                continue
            a = nibble_to_alpha(n)
            br, bg, bb = px[px_x, py]
            r = int(round(br * (1.0 - a) + fg_rgb[0] * a))
            g = int(round(bg * (1.0 - a) + fg_rgb[1] * a))
            b = int(round(bb * (1.0 - a) + fg_rgb[2] * a))
            px[px_x, py] = (r, g, b)


def _render_contact_sheet(
    ext_font: bytes,
    dim: int,
    vwf_map: dict[int, tuple[int, int]],
    out_path: str | Path,
    zoom: int = 2,
) -> str:
    """Render side-by-side contact sheet comparing vanilla A-Z/a-z and 0x88..0xA1."""
    rows_spec: list[tuple[str, list[int]]] = [
        ("Vanilla A-Z (row 1)", [ord(c) for c in "ABCDEFGHIJKLM"]),
        ("Vanilla A-Z (row 2)", [ord(c) for c in "NOPQRSTUVWXYZ"]),
        ("Vanilla a-z (row 1)", [ord(c) for c in "abcdefghijklm"]),
        ("Vanilla a-z (row 2)", [ord(c) for c in "nopqrstuvwxyz"]),
        ("PT-BR Lower + Cedilla (0x88..0x93)", list(range(0x88, 0x94))),
        ("PT-BR Upper + Cedilla (0x94..0x9F)", list(range(0x94, 0xA0))),
        ("PT-BR Ordinals & Pair Compare", [0xA0, 0xA1, ord("a"), 0x88, 0x89, 0x8A, 0x8B, ord("e"), 0x8C, 0x8D, ord("i"), 0x8E, ord("c"), 0x93]),
        ("Upper Pair Compare", [ord("A"), 0x94, 0x95, 0x96, 0x97, ord("E"), 0x98, 0x99, ord("I"), 0x9A, ord("O"), 0x9B, 0x9C, 0x9D]),
        ("Upper U/C + Ord Compare", [ord("U"), 0x9E, ord("C"), 0x9F, ord("1"), 0xA0, ord("1"), 0xA1, ord("O"), ord("P"), 0x9F, 0x9D, ord("E"), ord("S")]),
    ]
    cols = max(len(codes) for _, codes in rows_spec)
    cell_w = dim + 6
    cell_h = dim + 10
    label_h = 14
    margin = 8
    img_w = margin * 2 + cols * cell_w
    img_h = margin * 2 + len(rows_spec) * (cell_h + label_h)

    bg = (16, 26, 56)
    img = Image.new("RGB", (img_w, img_h), bg)
    draw = ImageDraw.Draw(img)

    baseline_y = 20 if dim == 24 else 13
    for r_idx, (title, codes) in enumerate(rows_spec):
        ry = margin + r_idx * (cell_h + label_h)
        draw.text((margin, ry), title, fill=(180, 210, 255))
        gy = ry + label_h
        for c_idx, code in enumerate(codes):
            gx = margin + c_idx * cell_w
            # Cell frame and subtle baseline guide
            is_ptbr = code >= PTBR_START_CODE
            frame_col = (55, 95, 145) if is_ptbr else (35, 50, 88)
            draw.rectangle([gx, gy, gx + dim + 1, gy + dim + 1], outline=frame_col)
            draw.line(
                [(gx + 1, gy + 1 + baseline_y), (gx + dim, gy + 1 + baseline_y)],
                fill=(45, 65, 105),
            )
            grid = decode_glyph_4bpp(ext_font, code - 0x20, dim)
            _blit_glyph_rgb(img, grid, gx + 1, gy + 1, bg_rgb=bg)

    if zoom > 1:
        img = img.resize((img_w * zoom, img_h * zoom), Image.Resampling.NEAREST)
    out = Path(out_path)
    img.save(out)
    return str(out)


def _encode_sample_text(text: str) -> bytes:
    out = bytearray()
    for ch in text:
        if ch in CHAR_TO_BYTE:
            out.append(CHAR_TO_BYTE[ch])
        else:
            code = ord(ch)
            if not (0x20 <= code <= 0x7D):
                raise ValueError(f"Unsupported sample char: {ch!r}")
            out.append(code)
    return bytes(out)


def _render_vwf_line(
    img: Image.Image,
    text: str,
    ext_font: bytes,
    dim: int,
    vwf_table: dict[int, tuple[int, int]],
    start_x: int,
    start_y: int,
    fixed_step: int | None = None,
) -> int:
    """Render a line of PT-BR text with exact Capcom VWF (or fixed step) positioning."""
    x = start_x
    for byte in _encode_sample_text(text):
        gid = byte - 0x20
        grid = decode_glyph_4bpp(ext_font, gid, dim)
        if fixed_step is not None:
            _blit_glyph_rgb(img, grid, x, start_y)
            x += fixed_step
        else:
            lb, adv = vwf_table[byte]
            if byte == 0x20:
                x += adv if adv > 0 else (dim // 3)
            else:
                _blit_glyph_rgb(img, grid, x - lb, start_y)
                x += adv
    return x - start_x


def render_qa_pngs(
    init_dat_bytes: bytes,
    exe_bytes: bytes,
    out_dir: str | Path = "/tmp",
) -> dict[str, str]:
    """Generate the 3 visual QA PNGs in out_dir and return their file paths."""
    font16_raw, font24_raw = extract_init_fonts(init_dat_bytes)
    ext16, ptbr_vwf16 = synthesize_ptbr_glyphs(font16_raw, 16)
    ext24, ptbr_vwf24 = synthesize_ptbr_glyphs(font24_raw, 24)

    # Load vanilla VWF_24 (Raw 0x33D0B0) and VWF_16 (Raw 0x33CFE0)
    full_vwf24: dict[int, tuple[int, int]] = {}
    full_vwf16: dict[int, tuple[int, int]] = {}
    for gid in range(VANILLA_GLYPH_COUNT):
        code = 0x20 + gid
        full_vwf24[code] = (
            exe_bytes[0x33D0B0 + gid * 2],
            exe_bytes[0x33D0B0 + gid * 2 + 1],
        )
        full_vwf16[code] = (
            exe_bytes[0x33CFE0 + gid * 2],
            exe_bytes[0x33CFE0 + gid * 2 + 1],
        )
    full_vwf24.update(ptbr_vwf24)
    full_vwf16.update(ptbr_vwf16)

    out_dir_p = Path(out_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)

    p24 = _render_contact_sheet(ext24, 24, full_vwf24, out_dir_p / "bof4_font_24.png", zoom=2)
    p16 = _render_contact_sheet(ext16, 16, full_vwf16, out_dir_p / "bof4_font_16.png", zoom=3)

    # Sample sentence PNG: required 24px VWF sentence + full upper/lower + 16px Title Menu preview
    sample_lines_24 = [
        "Olá! Você é o Ryu? Coração, ação, já, pão, 1º lugar! OPÇÕES",
        "Árvore, Às vezes, Ânimo, AÇÃO, Época, Êxito, Ídolo, Ótimo, Ônibus",
        "Õ, Único, Ç, 1ª vez, 2º andar -- bênção, manhã, próximo, fácil, útil, açúcar.",
    ]
    title_lines_16 = [
        "NOVO JOGO",
        "CARREGAR",
        "OPÇÕES",
        "MELHOR   NOVO RECORDE",
        "Olá! Você é o Ryu? Coração, ação, já, pão, 1º lugar! OPÇÕES",
    ]
    w, h = 1040, 290
    bg = (16, 26, 56)
    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)

    draw.text((12, 8), "24x24 Main Font (INIT.DAT[9]) - Capcom VWF Metrics:", fill=(180, 210, 255))
    y = 26
    for line in sample_lines_24:
        _render_vwf_line(img, line, ext24, 24, full_vwf24, 16, y)
        y += 32

    y += 10
    draw.line([(12, y - 4), (w - 12, y - 4)], fill=(60, 90, 140))
    draw.text((12, y), "16x16 UI Font (INIT.DAT[8]) - Title Menu (16px/char fixed) & VWF:", fill=(180, 210, 255))
    y += 18
    for idx, line in enumerate(title_lines_16):
        if idx < 4:
            # Title Menu uses 0x628C90 fixed-step (8px in 320px space = 16px native cell)
            _render_vwf_line(img, line, ext16, 16, full_vwf16, 16, y, fixed_step=16)
        else:
            _render_vwf_line(img, line, ext16, 16, full_vwf16, 16, y, fixed_step=None)
        y += 22

    sample_path = out_dir_p / "bof4_font_sample.png"
    img.save(sample_path)

    return {
        "font_24": p24,
        "font_16": p16,
        "sample": str(sample_path),
    }


if __name__ == "__main__":
    init_bytes = (DEFAULT_GAME_DIR / "DAT" / "INIT.DAT").read_bytes()
    exe_bytes = (DEFAULT_GAME_DIR / "BOF4.exe").read_bytes()
    paths = render_qa_pngs(init_bytes, exe_bytes, "/tmp")
    print("Generated QA PNGs:", paths)
    print("PTBR_VWF_24:", PTBR_VWF_24)
    print("PTBR_VWF_16:", PTBR_VWF_16)
