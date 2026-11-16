#!/usr/bin/env python3
"""Pre-render image guardrail for Quarto/LaTeX academic manuscripts.

Scans all `.qmd` files for image references and inspects assets in `images/`
to catch missing files, low-DPI raster figures, oversized rasters, and
unoptimized high-complexity vector PDFs before compilation.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from PIL import Image  # type: ignore

    HAS_PIL = True
except ImportError:
    Image = None
    HAS_PIL = False

RASTER_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
IMAGE_EXTENSIONS = RASTER_EXTENSIONS | {".pdf", ".eps", ".svg"}

MIN_DPI = 300.0
DPI_TOLERANCE = 0.5  # Handles 11811 px/m -> 299.9994 DPI rounding
MIN_PRINT_WIDTH_PX = 1050  # ~3.5 in single-column width at 300 DPI
MAX_RASTER_BYTES = 15 * 1024 * 1024  # 15 MB
MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB

MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+[\"'][^\"']*[\"'])?\)")
HTML_IMG_RE = re.compile(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.IGNORECASE)
TEX_IMG_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")


@dataclass
class ImageMetadata:
    width_px: Optional[int] = None
    height_px: Optional[int] = None
    dpi_x: Optional[float] = None
    dpi_y: Optional[float] = None
    pages: Optional[int] = None


@dataclass
class ValidationReport:
    warnings: list[str] = field(default_factory=list)
    reminders: list[str] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)


def strip_code_blocks(text: str) -> str:
    """Remove fenced markdown code blocks so example snippets are not treated as figures."""
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def extract_image_refs(qmd_path: Path) -> list[str]:
    """Extract local image references from a .qmd file."""
    raw_text = qmd_path.read_text(encoding="utf-8")
    cleaned = strip_code_blocks(raw_text)
    refs: list[str] = []
    for pattern in (MD_IMAGE_RE, HTML_IMG_RE, TEX_IMG_RE):
        for match in pattern.findall(cleaned):
            target = match.strip()
            if not target or target.startswith(("http://", "https://", "data:", "#")):
                continue
            refs.append(target)
    return refs


def resolve_ref_path(ref: str, qmd_path: Path, root: Path) -> Path:
    """Resolve an image reference relative to project root or the referencing .qmd."""
    clean_ref = ref.lstrip("/") if ref.startswith("/") else ref
    root_candidate = root / clean_ref
    if root_candidate.exists():
        return root_candidate
    local_candidate = qmd_path.parent / clean_ref
    if local_candidate.exists():
        return local_candidate
    return root_candidate


def parse_png_fallback(path: Path) -> ImageMetadata:
    """Parse PNG dimensions and DPI (pHYs chunk) using Python stdlib only."""
    meta = ImageMetadata()
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return meta

    pos = 8
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        chunk_type = data[pos + 4 : pos + 8]
        chunk_data = data[pos + 8 : pos + 8 + length]
        if chunk_type == b"IHDR" and len(chunk_data) >= 8:
            meta.width_px, meta.height_px = struct.unpack(">II", chunk_data[:8])
        elif chunk_type == b"pHYs" and len(chunk_data) >= 9:
            ppu_x, ppu_y, unit = struct.unpack(">IIB", chunk_data[:9])
            if unit == 1 and ppu_x > 0 and ppu_y > 0:
                meta.dpi_x = ppu_x * 0.0254
                meta.dpi_y = ppu_y * 0.0254
        elif chunk_type == b"IEND":
            break
        pos += 12 + length
    return meta


def parse_jpeg_fallback(path: Path) -> ImageMetadata:
    """Parse JPEG SOF dimensions and JFIF APP0 DPI using Python stdlib only."""
    meta = ImageMetadata()
    data = path.read_bytes()
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return meta

    pos = 2
    sof_markers = {
        0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
    }
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            pos += 1
            continue
        while pos < len(data) and data[pos] == 0xFF:
            pos += 1
        if pos >= len(data):
            break
        marker = data[pos]
        pos += 1
        if marker in (0xD8, 0xD9) or (0xD0 <= marker <= 0xD7):
            continue
        if pos + 2 > len(data):
            break
        seg_len = struct.unpack(">H", data[pos : pos + 2])[0]
        seg = data[pos + 2 : pos + seg_len]
        if marker == 0xE0 and len(seg) >= 12 and seg[:5] == b"JFIF\x00":
            units = seg[7]
            xdens, ydens = struct.unpack(">HH", seg[8:12])
            if units == 1 and xdens > 0 and ydens > 0:
                meta.dpi_x = float(xdens)
                meta.dpi_y = float(ydens)
            elif units == 2 and xdens > 0 and ydens > 0:
                meta.dpi_x = xdens * 2.54
                meta.dpi_y = ydens * 2.54
        elif marker in sof_markers and len(seg) >= 5:
            meta.height_px, meta.width_px = struct.unpack(">HH", seg[1:5])
            break
        pos += seg_len
    return meta


def inspect_raster(path: Path) -> ImageMetadata:
    """Inspect raster dimensions and DPI metadata."""
    if HAS_PIL and Image is not None:
        try:
            with Image.open(path) as img:
                width, height = img.size
                dpi_info = img.info.get("dpi")
                dpi_x = float(dpi_info[0]) if dpi_info and len(dpi_info) >= 2 else None
                dpi_y = float(dpi_info[1]) if dpi_info and len(dpi_info) >= 2 else None
                return ImageMetadata(width_px=width, height_px=height, dpi_x=dpi_x, dpi_y=dpi_y)
        except Exception:
            pass

    suffix = path.suffix.lower()
    if suffix == ".png":
        return parse_png_fallback(path)
    if suffix in {".jpg", ".jpeg"}:
        return parse_jpeg_fallback(path)
    return ImageMetadata()


def inspect_pdf(path: Path) -> ImageMetadata:
    """Inspect PDF page count via `pdfinfo` if available."""
    meta = ImageMetadata()
    if shutil.which("pdfinfo") is None:
        return meta
    try:
        proc = subprocess.run(
            ["pdfinfo", str(path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        for line in proc.stdout.splitlines():
            if line.startswith("Pages:"):
                meta.pages = int(line.split(":", 1)[1].strip())
                break
    except Exception:
        pass
    return meta


def format_mb(size_bytes: int) -> str:
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def validate_project(root: Path) -> ValidationReport:
    report = ValidationReport()
    images_dir = root / "images"

    qmd_files = sorted(
        p for p in root.rglob("*.qmd")
        if "build" not in p.parts and ".quarto" not in p.parts
    )

    referenced_paths: set[Path] = set()
    missing_seen: set[tuple[Path, str]] = set()

    for qmd in qmd_files:
        for ref in extract_image_refs(qmd):
            resolved = resolve_ref_path(ref, qmd, root)
            if not resolved.exists():
                key = (qmd, ref)
                if key not in missing_seen:
                    missing_seen.add(key)
                    rel_qmd = qmd.relative_to(root)
                    report.warnings.append(
                        f"Missing referenced image '{ref}' (cited in {rel_qmd})."
                    )
            else:
                referenced_paths.add(resolved.resolve())

    disk_images: list[Path] = []
    if images_dir.exists():
        disk_images = sorted(
            p for p in images_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        )

    all_to_inspect = sorted({p.resolve() for p in disk_images} | referenced_paths)

    if not all_to_inspect:
        report.infos.append("No image files found in images/ or referenced in .qmd files.")
        return report

    print(f"Inspecting {len(all_to_inspect)} figure asset(s)...")
    for img_path in all_to_inspect:
        try:
            rel_path = img_path.relative_to(root)
        except ValueError:
            rel_path = img_path

        size_bytes = img_path.stat().st_size
        suffix = img_path.suffix.lower()
        used_tag = "used" if img_path.resolve() in referenced_paths else "unused"

        if suffix in RASTER_EXTENSIONS:
            meta = inspect_raster(img_path)
            dim_str = (
                f"{meta.width_px}x{meta.height_px} px"
                if meta.width_px and meta.height_px
                else "unknown px"
            )
            dpi_str = (
                f"{meta.dpi_x:.0f}x{meta.dpi_y:.0f} DPI"
                if meta.dpi_x and meta.dpi_y
                else "no DPI metadata"
            )
            print(f"  - {rel_path} [{used_tag}] ({dim_str}, {dpi_str}, {format_mb(size_bytes)})")

            if meta.dpi_x is not None and meta.dpi_y is not None:
                min_dpi = min(meta.dpi_x, meta.dpi_y)
                if min_dpi < (MIN_DPI - DPI_TOLERANCE):
                    report.warnings.append(
                        f"Low DPI ({min_dpi:.0f} DPI < 300 DPI): {rel_path} "
                        f"({dim_str}). Re-export at >= 300 DPI for print."
                    )
            elif meta.width_px is not None and meta.width_px < MIN_PRINT_WIDTH_PX:
                report.warnings.append(
                    f"Missing DPI metadata and narrow width ({meta.width_px} px < "
                    f"{MIN_PRINT_WIDTH_PX} px): {rel_path}."
                )
            elif meta.width_px is not None:
                report.infos.append(
                    f"{rel_path} has no embedded DPI tag (width={meta.width_px} px; "
                    "verify print scale in GIS export)."
                )

            if meta.width_px is not None and meta.width_px < MIN_PRINT_WIDTH_PX:
                if meta.dpi_x is not None and min(meta.dpi_x, meta.dpi_y or meta.dpi_x) >= (MIN_DPI - DPI_TOLERANCE):
                    report.warnings.append(
                        f"Insufficient pixel width for print ({meta.width_px} px < "
                        f"{MIN_PRINT_WIDTH_PX} px): {rel_path}."
                    )

            if size_bytes > MAX_RASTER_BYTES:
                report.warnings.append(
                    f"Oversized raster ({format_mb(size_bytes)} > 15.00 MB): {rel_path}. "
                    "Downsample or compress to prevent LaTeX memory/compile slowdowns."
                )

        elif suffix == ".pdf":
            meta = inspect_pdf(img_path)
            pages_str = f"{meta.pages} page(s)" if meta.pages else "PDF"
            print(f"  - {rel_path} [{used_tag}] ({pages_str}, {format_mb(size_bytes)})")

            if size_bytes > MAX_PDF_BYTES:
                report.reminders.append(
                    f"Large vector PDF ({format_mb(size_bytes)} > 10.00 MB): {rel_path}. "
                    "Unoptimized high-complexity vector maps can stall pdflatex; "
                    "consider flattening dense layers or rasterizing at 300-600 DPI."
                )
        else:
            print(f"  - {rel_path} [{used_tag}] ({format_mb(size_bytes)})")

        if used_tag == "unused" and images_dir in img_path.parents:
            report.infos.append(
                f"Unused asset in images/: {rel_path} (will be excluded by 'make arxiv')."
            )

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate manuscript figure references, DPI, dimensions, and file sizes."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root directory (defaults to parent of scripts/).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero status if any warnings are raised.",
    )
    parser.add_argument(
        "--move-tex",
        action="store_true",
        help="Quarto post-render hook: move root index.tex into build/ output dir.",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    if args.move_tex:
        output_dir = Path(os.environ.get("QUARTO_PROJECT_OUTPUT_DIR", "build"))
        if not output_dir.is_absolute():
            output_dir = root / output_dir
        src_tex = root / "index.tex"
        if src_tex.is_file():
            output_dir.mkdir(parents=True, exist_ok=True)
            dest_tex = output_dir / "index.tex"
            shutil.move(str(src_tex), str(dest_tex))
            print(f"[OK] Moved {src_tex.name} -> {dest_tex}")
        return 0

    report = validate_project(root)

    print("")
    for info in report.infos:
        print(f"[INFO]     {info}")
    for rem in report.reminders:
        print(f"[REMINDER] {rem}")
    for warn in report.warnings:
        print(f"[WARNING]  {warn}")

    if not report.warnings and not report.reminders:
        print("[OK] All referenced figures and images/ assets passed pre-render checks.")

    if args.strict and report.warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
