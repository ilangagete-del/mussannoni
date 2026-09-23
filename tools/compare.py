"""Render reference and generated PDFs side by side for visual inspection."""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "compare"


def page_png(pdf: Path, index: int, zoom: float = 2.0) -> Image.Image:
    doc = pymupdf.open(pdf)
    page = doc[index]
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()
    return img


def side_by_side(reference: Path, generated: Path, index: int, label: str) -> Path:
    a = page_png(reference, index)
    b = page_png(generated, index)
    h = max(a.height, b.height)
    gap = 16
    canvas = Image.new("RGB", (a.width + b.width + gap, h), "#888888")
    canvas.paste(a, (0, 0))
    canvas.paste(b, (a.width + gap, 0))
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"{label}-p{index + 1}.png"
    canvas.save(target)
    return target


if __name__ == "__main__":
    name = sys.argv[1]
    page = int(sys.argv[2]) - 1 if len(sys.argv) > 2 else 0
    candidates = list((ROOT / "data" / "sars").rglob(f"*{name}*.pdf"))
    ref = next(c for c in candidates if "output" not in str(c))
    gen = ROOT / "output" / "pdf" / f"{ref.stem}.pdf"
    print(side_by_side(ref, gen, page, ref.stem))
