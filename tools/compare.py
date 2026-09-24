"""Render reference and generated PDFs side by side for visual inspection.

Usage::

    python tools/compare.py                      # page 1 of every document
    python tools/compare.py "10 BEST SCHOOLS"    # page 1 of one document
    python tools/compare.py "10 BEST SCHOOLS" 3  # page 3 of one document
    python tools/compare.py --template           # compare the templated output

Images land in per-kind subfolders of ``output/compare/`` so names never
collide and every report has a predictable set of artefacts. The reference is
always on the left and the generated output on the right, each labelled.

By default the right-hand side is the **conversion** output (``output/pdf/``),
which redraws a specific reference PDF; those side-by-sides are written to
``output/compare/conversion/<name> - page N.jpg``. With ``--template`` it is the
**templated** output (``output/template_pdf/``), rebuilt from data alone by
``sars template``, written to ``output/compare/template/<name> - page N.jpg``.
The ``<name> - page N`` stem is identical across both kinds; only the subfolder
disambiguates. A template reflows, so expect its page breaks to differ from the
reference - what matters there is that no value is missing.

The companion ``tools/pixel_diff.py`` writes lossless pixel diagnostics to a
third subfolder, ``output/compare/pixel/``.
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


def side_by_side(
    reference: Path,
    generated: Path,
    index: int,
    stem: str,
    subdir: str,
    right_label: str = "GENERATED A4",
) -> Path:
    left = _labelled(page_image(reference, index), f"REFERENCE  -  {reference.name}")
    right = _labelled(page_image(generated, index), f"{right_label}  -  {generated.name}")
    height = max(left.height, right.height)
    canvas = Image.new("RGB", (left.width + right.width + GAP, height), "#9aa5b1")
    canvas.paste(left, (0, 0))
    canvas.paste(right, (left.width + GAP, 0))
    out_dir = OUT / subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{stem} - page {index + 1}.jpg"
    canvas.save(target, "JPEG", quality=82, optimize=True)
    return target


def _pairs():
    sys.path.insert(0, str(ROOT / "src"))
    from sars import sources

    return sources.discover()


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    templated = "--template" in sys.argv
    needle = args[0] if args else None
    page = int(args[1]) - 1 if len(args) > 1 else 0

    if templated:
        source_dir = ROOT / "output" / "template_pdf"
        subdir, right_label, rebuild = "template", "FROM DATA (template)", "sars template"
    else:
        source_dir = ROOT / "output" / "pdf"
        subdir, right_label, rebuild = "conversion", "GENERATED A4", "sars all"

    pairs = _pairs()
    if needle:
        pairs = [p for p in pairs if needle.lower() in p.name.lower()]
        if not pairs:
            print(f"no document matches {needle!r}", file=sys.stderr)
            return 1

    for pair in pairs:
        generated = source_dir / f"{pair.name}.pdf"
        if not generated.exists():
            print(f"skip {pair.name}: no PDF (run `{rebuild}`)", file=sys.stderr)
            continue
        target = side_by_side(
            pair.pdf, generated, page, pair.name, subdir, right_label=right_label
        )
        print(target.relative_to(OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
