"""Lossless pixel-by-pixel *metrics* for generated vs reference PDFs.

This is the NUMBERS tool: it rasterises both pages with the same matrix,
requires identical page pixel dimensions, and reports exact / thresholded
mismatch counts plus MAE / RMSE / PSNR. It does **not** write any image files -
the single visual comparison per report (reference | template | diff) is written
by ``tools/compare.py`` as ``output/compare/<name>.jpg`` and overwritten in
place. Keeping the images in one place avoids the old pile-up of per-kind and
per-page files.

Usage::

    python tools/pixel_diff.py "MWANZA CC SCHOOLS RANK" --template
    python tools/pixel_diff.py "MWANZA CC SCHOOLS RANK" --template --zoom 4
    python tools/pixel_diff.py --all --template   # every report, page 1

In ``--all`` batch mode the tool iterates every discovered report and prints one
result line per report (exact% / visible% match, or ``DIMENSION MISMATCH: ...``
when the generated page size differs from the reference). Reports that mismatch
are listed explicitly, never silently skipped.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]


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


def _discover():
    sys.path.insert(0, str(ROOT / "src"))
    from sars import sources

    return sources.discover()


def _generated_for(pair, templated: bool) -> Path:
    directory = "template_pdf" if templated else "pdf"
    return ROOT / "output" / directory / f"{pair.name}.pdf"


def select_pair(name: str, templated: bool) -> tuple[str, Path, Path]:
    pairs = _discover()
    exact = [pair for pair in pairs if pair.name.casefold() == name.casefold()]
    matches = exact or [pair for pair in pairs if name.casefold() in pair.name.casefold()]
    if len(matches) != 1:
        found = ", ".join(pair.name for pair in matches) or "none"
        raise ValueError(f"report name must select exactly one document; matched: {found}")
    pair = matches[0]
    generated = _generated_for(pair, templated)
    if not generated.exists():
        raise FileNotFoundError(generated)
    return pair.name, pair.pdf, generated


def compare_one(name: str, reference_pdf: Path, generated_pdf: Path, page: int, zoom: float):
    """Run a single-page metric comparison.

    Returns ``(metrics, ref_size, None)`` when sizes match, or
    ``(None, ref_size, gen_size)`` on a dimension mismatch. Writes no images.
    """
    reference = raster(reference_pdf, page - 1, zoom)
    generated = raster(generated_pdf, page - 1, zoom)
    if reference.size != generated.size:
        return None, reference.size, generated.size
    result = metrics(reference, generated)
    return result, (reference.width, reference.height), None


def run_all(templated: bool, page: int, zoom: float) -> int:
    pairs = _discover()
    mismatched: list[str] = []
    failures = 0
    print(f"pixel comparison of {len(pairs)} reports (page {page} @ {zoom:g}x)")
    for pair in sorted(pairs, key=lambda p: p.name.casefold()):
        generated_pdf = _generated_for(pair, templated)
        if not generated_pdf.exists():
            rebuild = "sars template" if templated else "sars all"
            print(f"{pair.name}: MISSING PDF (run `{rebuild}`)")
            mismatched.append(pair.name)
            failures += 1
            continue
        try:
            result, ref_size, gen_size = compare_one(pair.name, pair.pdf, generated_pdf, page, zoom)
        except ValueError as error:
            print(f"{pair.name}: {error}")
            mismatched.append(pair.name)
            failures += 1
            continue
        if result is None:
            print(f"{pair.name}: DIMENSION MISMATCH: reference={ref_size} generated={gen_size}")
            mismatched.append(pair.name)
            continue
        if result["exact_mismatch"]:
            failures += 1
        print(
            f"{pair.name}: exact {result['exact_match_pct']:.4f}% / "
            f"visible {result['visible_match_pct']:.4f}% "
            f"(max_delta={result['max_delta']}) {ref_size[0]}x{ref_size[1]}px"
        )

    print()
    if mismatched:
        print(f"DIMENSION MISMATCH / missing ({len(mismatched)}): " + "; ".join(mismatched))
    else:
        print("all reports matched dimensions")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", nargs="?", help="report name (substring); omit with --all")
    parser.add_argument("--all", action="store_true", help="compare every discovered report")
    parser.add_argument("--template", action="store_true")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--zoom", type=float, default=2.0)
    args = parser.parse_args()

    if args.all:
        return run_all(args.template, args.page, args.zoom)

    if not args.name:
        parser.error("a report name is required unless --all is given")

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
    return 0 if result["exact_mismatch"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
