"""One comparison image per report, overwritten in place each run.

For every report this writes exactly ONE file, ``output/compare/<name>.jpg``,
and overwrites it on each run - no per-page, per-kind, or diagnostic variants
piling up. The single panel places three views of page 1 side by side, each
labelled:

    REFERENCE            |  TEMPLATE (from data)  |  DIFF
    the original PDF        the data-driven          red = pixels that differ
                            template output          (only when page sizes match)

When the template page size matches the reference (the fixed-layout goal), the
DIFF panel is a lossless red-on-white heatmap and the label carries the exact /
visible pixel-match percentages. When sizes differ, the DIFF panel says so
instead of drawing a meaningless overlay.

Usage::

    python tools/compare.py                       # every report, one image each
    python tools/compare.py "SCHOOLS RANK"        # just the matching report(s)
    python tools/compare.py --conversion          # right panel = conversion PDF
    python tools/compare.py --page 3              # compare page 3 instead of 1

By default the middle/right panels use the **template** output
(``output/template_pdf/``), rebuilt from data by ``sars template``. Pass
``--conversion`` to compare the **conversion** output (``output/pdf/``) instead;
the single per-report file name is unchanged, so it still overwrites in place.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops, ImageDraw, ImageEnhance

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "compare"

ZOOM = 2.0
BAR = 26
GAP = 14


def page_image(pdf: Path, index: int, zoom: float = ZOOM) -> Image.Image:
    doc = pymupdf.open(pdf)
    page = doc[min(index, doc.page_count - 1)]
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False, colorspace=pymupdf.csRGB)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()
    return img


def _labelled(img: Image.Image, label: str) -> Image.Image:
    canvas = Image.new("RGB", (img.width, img.height + BAR), "#ffffff")
    canvas.paste(img, (0, BAR))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, img.width, BAR - 1], fill="#1f2933")
    draw.text((8, 7), label, fill="#ffffff")
    return canvas


def _pixel_stats(reference: Image.Image, generated: Image.Image) -> tuple[float, float]:
    """Return (exact%, visible%) pixel-match percentages for equal-size images."""
    ref = reference.load()
    gen = generated.load()
    exact_diff = 0
    visible_diff = 0
    for y in range(reference.height):
        for x in range(reference.width):
            delta = max(abs(a - b) for a, b in zip(ref[x, y], gen[x, y], strict=True))
            if delta:
                exact_diff += 1
            if delta > 8:
                visible_diff += 1
    total = reference.width * reference.height
    return 100 * (total - exact_diff) / total, 100 * (total - visible_diff) / total


def _diff_panel(reference: Image.Image, generated: Image.Image) -> tuple[Image.Image, str]:
    """Build the DIFF panel and its label.

    Equal sizes -> lossless red-on-white heatmap + pixel-match label.
    Different sizes -> a plain notice panel (no misleading overlay).
    """
    if reference.size == generated.size:
        exact_pct, visible_pct = _pixel_stats(reference, generated)
        raw = ImageChops.difference(reference, generated)
        mask = ImageEnhance.Contrast(raw).enhance(4.0).convert("L")
        heatmap = Image.new("RGB", raw.size, "#ffffff")
        heatmap.paste(Image.new("RGB", raw.size, "#ff0000"), mask=mask)
        return heatmap, f"DIFF  -  exact {exact_pct:.1f}% / visible {visible_pct:.1f}%"

    panel = Image.new("RGB", reference.size, "#ffffff")
    draw = ImageDraw.Draw(panel)
    draw.text(
        (10, 10),
        "PAGE SIZE DIFFERS\n"
        f"reference {reference.width}x{reference.height}\n"
        f"generated {generated.width}x{generated.height}\n"
        "(no pixel diff possible)",
        fill="#b91c1c",
    )
    return panel, "DIFF  -  size mismatch"


def compare_one(reference: Path, generated: Path, index: int, right_label: str) -> Path:
    """Write the single ``output/compare/<name>.jpg`` panel for one report."""
    ref_img = page_image(reference, index)
    gen_img = page_image(generated, index)
    diff_img, diff_label = _diff_panel(ref_img, gen_img)

    left = _labelled(ref_img, f"REFERENCE  -  {reference.name}")
    middle = _labelled(gen_img, right_label)
    right = _labelled(diff_img, diff_label)

    height = max(left.height, middle.height, right.height)
    width = left.width + middle.width + right.width + 2 * GAP
    canvas = Image.new("RGB", (width, height), "#9aa5b1")
    x = 0
    for panel in (left, middle, right):
        canvas.paste(panel, (x, 0))
        x += panel.width + GAP

    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"{reference.stem}.jpg"  # ONE file per report, overwritten in place.
    canvas.save(target, "JPEG", quality=82, optimize=True)
    return target


def _pairs():
    sys.path.insert(0, str(ROOT / "src"))
    from sars import sources

    return sources.discover()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", nargs="?", help="report name (substring); omit for all")
    parser.add_argument(
        "--conversion",
        action="store_true",
        help="compare the conversion output (output/pdf) instead of the template output",
    )
    parser.add_argument("--page", type=int, default=1, help="1-based page to compare (default 1)")
    args = parser.parse_args()

    if args.conversion:
        source_dir = ROOT / "output" / "pdf"
        right_label, rebuild = "CONVERSION", "sars all"
    else:
        source_dir = ROOT / "output" / "template_pdf"
        right_label, rebuild = "TEMPLATE (from data)", "sars template"

    pairs = _pairs()
    if args.name:
        pairs = [p for p in pairs if args.name.lower() in p.name.lower()]
        if not pairs:
            print(f"no document matches {args.name!r}", file=sys.stderr)
            return 1

    index = args.page - 1
    exit_code = 0
    for pair in sorted(pairs, key=lambda p: p.name.casefold()):
        generated = source_dir / f"{pair.name}.pdf"
        if not generated.exists():
            print(f"skip {pair.name}: no PDF (run `{rebuild}`)", file=sys.stderr)
            exit_code = 1
            continue
        target = compare_one(pair.pdf, generated, index, right_label)
        print(target.relative_to(OUT))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
