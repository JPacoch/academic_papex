#!/usr/bin/env python3
"""Generate clean, print-grade (300 DPI) sample PNG and vector PDF figures.

Produces realistic geoinformatics placeholder figures in `images/` using Python's
standard library only so the initial pipeline builds out of the box even before
optional image-processing packages are installed.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path
from typing import Callable

PPM_300_DPI = 11812  # 11812 px/m * 0.0254 m/in = 300.02 DPI

ColorStop = tuple[float, tuple[int, int, int]]


def lerp_palette(value: float, stops: list[ColorStop]) -> tuple[int, int, int]:
    """Interpolate an RGB color along sorted normalized [0, 1] stops."""
    v = max(0.0, min(1.0, value))
    for idx in range(len(stops) - 1):
        t0, c0 = stops[idx]
        t1, c1 = stops[idx + 1]
        if v <= t1:
            alpha = (v - t0) / max(1e-9, (t1 - t0))
            return (
                int(c0[0] + alpha * (c1[0] - c0[0])),
                int(c0[1] + alpha * (c1[1] - c0[1])),
                int(c0[2] + alpha * (c1[2] - c0[2])),
            )
    return stops[-1][1]


def build_palette_lut(stops: list[ColorStop], size: int = 256) -> list[bytes]:
    """Precompute a 256-entry RGB byte lookup table for fast PNG raster generation."""
    return [bytes(lerp_palette(i / (size - 1), stops)) for i in range(size)]


TERRAIN_LUT = build_palette_lut([
    (0.00, (24, 58, 92)),
    (0.25, (42, 128, 114)),
    (0.50, (124, 179, 98)),
    (0.75, (214, 184, 110)),
    (0.92, (166, 118, 92)),
    (1.00, (244, 246, 248)),
])

SLOPE_LUT = build_palette_lut([
    (0.00, (25, 22, 48)),
    (0.30, (108, 36, 112)),
    (0.60, (206, 74, 72)),
    (0.85, (246, 162, 58)),
    (1.00, (252, 244, 176)),
])

NDVI_LUT = build_palette_lut([
    (0.00, (132, 94, 62)),
    (0.35, (194, 174, 112)),
    (0.65, (108, 174, 78)),
    (1.00, (18, 96, 44)),
])

UNCERTAINTY_LUT = build_palette_lut([
    (0.00, (240, 246, 252)),
    (0.30, (166, 206, 232)),
    (0.65, (72, 138, 196)),
    (0.88, (224, 96, 62)),
    (1.00, (158, 22, 34)),
])


def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    """Serialize a PNG chunk with CRC32."""
    length = struct.pack(">I", len(data))
    crc = struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    return length + chunk_type + data + crc


def write_png(
    path: Path,
    width: int,
    height: int,
    lut: list[bytes],
    field_fn: Callable[[float, float], float],
    contour_step: float = 0.0,
) -> None:
    """Write an 8-bit RGB PNG with 300 DPI pHYs metadata using pure stdlib."""
    raw_rows = bytearray()
    border = 6
    inv_w = 1.0 / max(1, width - 1)
    inv_h = 1.0 / max(1, height - 1)

    # Precompute coarse grid and bilinearly upsample for crisp, fast generation
    coarse_step = 4
    cw = (width // coarse_step) + 2
    ch = (height // coarse_step) + 2
    grid = [
        [field_fn((gx * coarse_step) * inv_w, (gy * coarse_step) * inv_h) for gx in range(cw)]
        for gy in range(ch)
    ]

    dark_border = b"\x22\x26\x2d"
    contour_rgb = b"\x28\x2c\x34"

    for y in range(height):
        raw_rows.append(0)  # Filter type 0 (None)
        if y < border or y >= height - border:
            raw_rows.extend(dark_border * width)
            continue

        gy = y // coarse_step
        fy = (y % coarse_step) / coarse_step
        row0 = grid[gy]
        row1 = grid[gy + 1]

        row_bytes = bytearray(width * 3)
        for x in range(width):
            if x < border or x >= width - border:
                row_bytes[x * 3 : x * 3 + 3] = dark_border
                continue
            gx = x // coarse_step
            fx = (x % coarse_step) / coarse_step
            v00 = row0[gx]
            v10 = row0[gx + 1]
            v01 = row1[gx]
            v11 = row1[gx + 1]
            val = (
                v00 * (1.0 - fx) * (1.0 - fy)
                + v10 * fx * (1.0 - fy)
                + v01 * (1.0 - fx) * fy
                + v11 * fx * fy
            )
            if contour_step > 0.0 and (val % contour_step) < 0.008:
                row_bytes[x * 3 : x * 3 + 3] = contour_rgb
            else:
                idx = max(0, min(255, int(val * 255.0)))
                row_bytes[x * 3 : x * 3 + 3] = lut[idx]

        raw_rows.extend(row_bytes)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    phys = struct.pack(">IIB", PPM_300_DPI, PPM_300_DPI, 1)
    idat = zlib.compress(bytes(raw_rows), level=6)

    png_bytes = b"".join([
        b"\x89PNG\r\n\x1a\n",
        png_chunk(b"IHDR", ihdr),
        png_chunk(b"pHYs", phys),
        png_chunk(b"IDAT", idat),
        png_chunk(b"IEND", b""),
    ])
    path.write_bytes(png_bytes)


def terrain_elevation(u: float, v: float) -> float:
    """Synthetic alpine catchment elevation in [0, 1]."""
    ridge_1 = 0.55 * math.exp(-((u - 0.34) ** 2 / 0.035 + (v - 0.42) ** 2 / 0.05))
    ridge_2 = 0.65 * math.exp(-((u - 0.72) ** 2 / 0.045 + (v - 0.62) ** 2 / 0.04))
    valley = 0.28 * math.exp(-((v - (0.25 + 0.55 * u)) ** 2) / 0.012)
    ripple = 0.09 * math.sin(9.0 * u + 2.0 * v) * math.cos(7.0 * v - 1.5 * u)
    val = 0.36 + ridge_1 + ridge_2 - valley + ripple
    return max(0.0, min(1.0, val))


def terrain_slope(u: float, v: float) -> float:
    """Normalized terrain gradient magnitude in [0, 1]."""
    eps = 0.008
    dz_dx = (terrain_elevation(u + eps, v) - terrain_elevation(u - eps, v)) / (2.0 * eps)
    dz_dy = (terrain_elevation(u, v + eps) - terrain_elevation(u, v - eps)) / (2.0 * eps)
    mag = math.hypot(dz_dx, dz_dy)
    return max(0.0, min(1.0, mag / 4.2))


def ndvi_field(u: float, v: float) -> float:
    """Synthetic vegetation index negatively correlated with high elevation."""
    elev = terrain_elevation(u, v)
    spatial_mod = 0.12 * math.sin(6.5 * u) * math.cos(5.5 * v)
    return max(0.0, min(1.0, 0.92 - 0.85 * elev + spatial_mod))


def uncertainty_field(u: float, v: float) -> float:
    """Synthetic kriging standard error driven by slope and sample sparsity."""
    slope = terrain_slope(u, v)
    sparsity = 0.32 * math.exp(-((u - 0.80) ** 2 + (v - 0.25) ** 2) / 0.03)
    return max(0.0, min(1.0, 0.15 + 0.65 * slope + sparsity))


def write_pipeline_pdf(path: Path) -> None:
    """Write a crisp vector PDF 1.4 pipeline diagram using standard Helvetica Type1 font."""
    width_pt, height_pt = 540, 140
    boxes = [
        (20, 42, 108, 56, "LiDAR Point Cloud", "(n samples in R^2)"),
        (152, 42, 108, 56, "k-d Tree Index", "O(n log n) build"),
        (284, 42, 108, 56, "Local BLUP Solver", "Eq. (2) Cholesky"),
        (416, 42, 104, 56, "DEM & Error Grid", "0.5 m raster output"),
    ]

    stream_cmds: list[str] = [
        "q",
        "0.97 0.98 0.99 rg",
        f"4 4 {width_pt - 8} {height_pt - 8} re f",
        "0.80 0.84 0.89 RG 1 w",
        f"4 4 {width_pt - 8} {height_pt - 8} re S",
    ]

    for idx, (bx, by, bw, bh, title, subtitle) in enumerate(boxes):
        # Box fill and border
        stream_cmds.extend([
            "0.91 0.95 0.99 rg",
            f"{bx} {by} {bw} {bh} re f",
            "0.04 0.31 0.54 RG 1.4 w",
            f"{bx} {by} {bw} {bh} re S",
            # Title text
            "BT /F1 10 Tf 0.05 0.15 0.28 rg",
            f"1 0 0 1 {bx + 10} {by + 34} Tm ({title}) Tj ET",
            # Subtitle text
            "BT /F1 8 Tf 0.25 0.32 0.40 rg",
            f"1 0 0 1 {bx + 10} {by + 16} Tm ({subtitle}) Tj ET",
        ])
        if idx < len(boxes) - 1:
            ax1 = bx + bw + 2
            ax2 = boxes[idx + 1][0] - 2
            ay = by + bh / 2.0
            stream_cmds.extend([
                "0.04 0.31 0.54 RG 1.6 w",
                f"{ax1:.1f} {ay:.1f} m {ax2:.1f} {ay:.1f} l S",
                "0.04 0.31 0.54 rg",
                f"{ax2:.1f} {ay:.1f} m {ax2 - 6:.1f} {ay + 4:.1f} l {ax2 - 6:.1f} {ay - 4:.1f} l f",
            ])

    stream_cmds.append("Q")
    content_stream = "\n".join(stream_cmds).encode("latin-1")

    objects: list[bytes] = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        (
            f"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width_pt} {height_pt}] "
            "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
        ).encode("latin-1"),
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        (
            f"5 0 obj\n<< /Length {len(content_stream)} >>\nstream\n".encode("latin-1")
            + content_stream
            + b"\nendstream\nendobj\n"
        ),
    ]

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)

    xref_pos = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf.extend(f"{off:010d} 00000 n \n".encode("latin-1"))

    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n"
        ).encode("latin-1")
    )
    path.write_bytes(bytes(pdf))


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    images_dir = root / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    out_path = images_dir / "sample_dem.png"
    write_png(out_path, 1600, 1000, TERRAIN_LUT, terrain_elevation, contour_step=0.08)
    print(f"Generated {out_path.relative_to(root)} (1600x1000 px, 300 DPI)")


if __name__ == "__main__":
    main()
