"""Render reference and generated PDFs side by side for visual inspection.

Usage::

    python tools/compare.py                      # page 1 of every document
    python tools/compare.py "10 BEST SCHOOLS"    # page 1 of one document
    python tools/compare.py "10 BEST SCHOOLS" 3  # page 3 of one document

Images land in ``output/compare/``. The reference is always on the left and the
generated A4 output on the right, each labelled.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "compare"

ZOOM = 2.0
BAR = 26
GAP = 14


def page_image(pdf: Path, index: int, zoom: float = ZOOM) -> Image.Image:
    doc = pymupdf.open(pdf)
    page = doc[min(index, doc.page_count - 1)]
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
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


def side_by_side(reference: Path, generated: Path, index: int, label: str) -> Path:
    left = _labelled(page_image(reference, index), f"REFERENCE  -  {reference.name}")
    right = _labelled(page_image(generated, index), f"GENERATED A4  -  {generated.name}")
    height = max(left.height, right.height)
    canvas = Image.new("RGB", (left.width + right.width + GAP, height), "#9aa5b1")
    canvas.paste(left, (0, 0))
    canvas.paste(right, (left.width + GAP, 0))
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"{label} - page {index + 1}.jpg"
    canvas.save(target, "JPEG", quality=82, optimize=True)
    return target


def _pairs():
    sys.path.insert(0, str(ROOT / "src"))
    from sars import sources

    return sources.discover()


def main() -> int:
    needle = sys.argv[1] if len(sys.argv) > 1 else None
    page = int(sys.argv[2]) - 1 if len(sys.argv) > 2 else 0

    pairs = _pairs()
    if needle:
        pairs = [p for p in pairs if needle.lower() in p.name.lower()]
        if not pairs:
            print(f"no document matches {needle!r}", file=sys.stderr)
            return 1

    for pair in pairs:
        generated = ROOT / "output" / "pdf" / f"{pair.name}.pdf"
        if not generated.exists():
            print(f"skip {pair.name}: no output PDF (run `sars all`)", file=sys.stderr)
            continue
        print(side_by_side(pair.pdf, generated, page, pair.name).name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
