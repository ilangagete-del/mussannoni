"""Probe the reference PDFs: page geometry, orientation, table grid, fonts, fill colours.

Read-only diagnostic. The reference PDFs are ground truth and are never modified.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pdfplumber

DATA = Path(__file__).resolve().parents[1] / "data" / "sars"


def all_pdfs() -> list[Path]:
    pdfs = sorted(DATA.glob("*.pdf"))
    pdfs += sorted((DATA / "council_pdf").glob("*.pdf"))
    pdfs += sorted((DATA / "region_pdf").glob("*.pdf"))
    return pdfs


def probe(path: Path) -> None:
    with pdfplumber.open(path) as pdf:
        p0 = pdf.pages[0]
        w, h = float(p0.width), float(p0.height)
        orient = "landscape" if w > h else "portrait"
        print(f"\n=== {path.name}")
        print(f"    pages={len(pdf.pages)}  size={w:.0f}x{h:.0f}pt  {orient}")

        # fonts / sizes actually used
        fonts: dict[tuple[str, float], int] = {}
        colours: dict[tuple, int] = {}
        for ch in p0.chars:
            key = (ch["fontname"], round(float(ch["size"]), 1))
            fonts[key] = fonts.get(key, 0) + 1
            colours[ch.get("non_stroke_color")] = colours.get(ch.get("non_stroke_color"), 0) + 1
        print("    fonts:", sorted(fonts.items(), key=lambda kv: -kv[1])[:6])
        print("    text colours:", sorted(colours.items(), key=lambda kv: -kv[1])[:5])

        # filled rects = cell shading / header bands
        fills: dict[tuple, int] = {}
        for r in p0.rects:
            if r.get("fill"):
                fills[r.get("non_stroke_color")] = fills.get(r.get("non_stroke_color"), 0) + 1
        print(f"    rects={len(p0.rects)} lines={len(p0.lines)} curves={len(p0.curves)}")
        print("    fill colours:", sorted(fills.items(), key=lambda kv: -kv[1])[:8])

        # table detection from ruling lines
        tables = p0.find_tables()
        print(f"    tables detected on p0: {len(tables)}")
        for i, t in enumerate(tables):
            rows = t.extract()
            ncols = max((len(r) for r in rows), default=0)
            print(
                f"      table[{i}] rows={len(rows)} cols={ncols} bbox={[round(v) for v in t.bbox]}"
            )


if __name__ == "__main__":
    targets = all_pdfs()
    if len(sys.argv) > 1:
        needle = sys.argv[1].lower()
        targets = [p for p in targets if needle in p.name.lower()]
    for p in targets:
        probe(p)
