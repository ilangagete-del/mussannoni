"""Lossless pixel-by-pixel comparison of generated and reference PDFs.

Unlike ``compare.py`` this tool does not create a lossy JPEG or resize either
page.  It rasterises both pages with the same matrix, requires identical page
pixel dimensions, reports exact and thresholded mismatch counts, and writes a
PNG heatmap plus a PNG overlay for inspection.

Usage::

    python tools/pixel_diff.py "MWANZA CC SCHOOLS RANK" --template
    python tools/pixel_diff.py "MWANZA CC SCHOOLS RANK" --template --zoom 4
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops, ImageEnhance

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "compare"


def raster(pdf: Path, page_index: int, zoom: float) -> Image.Image:
    with pymupdf.open(pdf) as document:
        if page_index < 0 or page_index >= document.page_count:
            raise ValueError(f"{pdf.name} has {document.page_count} pages; page {page_index + 1} is invalid")
        pixmap = document[page_index].get_pixmap(
            matrix=pymupdf.Matrix(zoom, zoom), alpha=False, colorspace=pymupdf.csRGB
        )
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def metrics(reference: Image.Image, generated: Image.Image) -> dict[str, float | int]:
    difference = ImageChops.difference(reference, generated)
    histogram = difference.histogram()
    channel_samples = reference.width * reference.height * 3
    abs_sum = sum((index % 256) * count for index, count in enumerate(histogram))
    squared_sum = sum(((index % 256) ** 2) * count for index, count in enumerate(histogram))

    ref_pixels = reference.load()
    out_pixels = generated.load()
    exact_mismatch = 0
    visible_mismatch = 0
    max_delta = 0
    for y in range(reference.height):
        for x in range(reference.width):
            deltas = tuple(abs(a - b) for a, b in zip(ref_pixels[x, y], out_pixels[x, y], strict=True))
            delta = max(deltas)
            if delta:
                exact_mismatch += 1
            if delta > 8:
                visible_mismatch += 1
            max_delta = max(max_delta, delta)

    pixel_count = reference.width * reference.height
    mae = abs_sum / channel_samples
    rmse = math.sqrt(squared_sum / channel_samples)
    psnr = float("inf") if rmse == 0 else 20 * math.log10(255 / rmse)
    return {
        "pixels": pixel_count,
        "exact_mismatch": exact_mismatch,
        "exact_match_pct": 100 * (pixel_count - exact_mismatch) / pixel_count,
        "visible_mismatch": visible_mismatch,
        "visible_match_pct": 100 * (pixel_count - visible_mismatch) / pixel_count,
        "mae": mae,
        "rmse": rmse,
        "psnr": psnr,
        "max_delta": max_delta,
    }


def save_diagnostics(reference: Image.Image, generated: Image.Image, stem: str) -> tuple[Path, Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    raw = ImageChops.difference(reference, generated)
    amplified = ImageEnhance.Contrast(raw).enhance(4.0)
    heatmap = Image.new("RGB", raw.size, "white")
    mask = amplified.convert("L")
    red = Image.new("RGB", raw.size, "#ff0000")
    heatmap.paste(red, mask=mask)
    heatmap_path = OUT / f"PIXEL DIFF {stem}.png"
    heatmap.save(heatmap_path, "PNG", optimize=True)

    overlay = Image.blend(reference, generated, 0.5)
    overlay_path = OUT / f"PIXEL OVERLAY {stem}.png"
    overlay.save(overlay_path, "PNG", optimize=True)
    return heatmap_path, overlay_path


def select_pair(name: str, templated: bool) -> tuple[str, Path, Path]:
    sys.path.insert(0, str(ROOT / "src"))
    from sars import sources

    pairs = sources.discover()
    exact = [pair for pair in pairs if pair.name.casefold() == name.casefold()]
    matches = exact or [pair for pair in pairs if name.casefold() in pair.name.casefold()]
    if len(matches) != 1:
        found = ", ".join(pair.name for pair in matches) or "none"
        raise ValueError(f"report name must select exactly one document; matched: {found}")
    pair = matches[0]
    directory = "template_pdf" if templated else "pdf"
    generated = ROOT / "output" / directory / f"{pair.name}.pdf"
    if not generated.exists():
        raise FileNotFoundError(generated)
    return pair.name, pair.pdf, generated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("--template", action="store_true")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--zoom", type=float, default=2.0)
    args = parser.parse_args()

    try:
        name, reference_pdf, generated_pdf = select_pair(args.name, args.template)
        reference = raster(reference_pdf, args.page - 1, args.zoom)
        generated = raster(generated_pdf, args.page - 1, args.zoom)
        if reference.size != generated.size:
            print(
                f"DIMENSION MISMATCH: reference={reference.size} generated={generated.size}",
                file=sys.stderr,
            )
            return 2
        result = metrics(reference, generated)
        suffix = f"{'TEMPLATE ' if args.template else ''}{name} - page {args.page}"
        heatmap, overlay = save_diagnostics(reference, generated, suffix)
    except (FileNotFoundError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2

    print(f"{name} page {args.page} @ {args.zoom:g}x: {reference.width}x{reference.height}px")
    print(
        "exact: "
        f"{result['exact_match_pct']:.6f}% match, "
        f"{result['exact_mismatch']}/{result['pixels']} pixels differ"
    )
    print(
        "visible (max RGB delta > 8): "
        f"{result['visible_match_pct']:.6f}% match, "
        f"{result['visible_mismatch']}/{result['pixels']} pixels differ"
    )
    print(
        f"MAE={result['mae']:.6f} RMSE={result['rmse']:.6f} "
        f"PSNR={result['psnr']:.3f}dB max_delta={result['max_delta']}"
    )
    print(f"heatmap: {heatmap.relative_to(ROOT)}")
    print(f"overlay: {overlay.relative_to(ROOT)}")
    return 0 if result["exact_mismatch"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
