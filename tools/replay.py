"""Oracle replay: rebuild a reference page from its OWN primitives, in HTML.

This is a *measuring instrument*, not part of the product. It reads a reference
PDF's own drawing operators (filled rectangles) and its own text (every glyph,
with the exact origin the PDF places it at), emits that as absolutely positioned
HTML + CSS using the font assets that MuPDF actually draws, prints it with
WeasyPrint, and gates the result against the reference.

Its purpose is to answer one question honestly, before any renderer is touched:

    if the geometry, the colours, the fonts and every glyph position are exactly
    right, how close can WeasyPrint + MuPDF get to the reference?

That number is the ceiling for the templated renderers. Anything below it in a
renderer is the renderer's own defect; the gap between it and 100% is the
irreducible residual of this toolchain, and this tool is the evidence for it.

Usage::

    uv run python tools/replay.py --only "Wards Rank"
    uv run python tools/replay.py                 # every report
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sars import fonts, printing, sources  # noqa: E402

OUT_HTML = ROOT / "output" / "replay_html"
OUT_PDF = ROOT / "output" / "replay_pdf"


def _hex(color) -> str:
    if color is None:
        return "transparent"
    r, g, b = (max(0.0, min(1.0, c)) for c in color)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def _fills(page: pymupdf.Page) -> list[str]:
    out: list[str] = []
    for drawing in page.get_drawings():
        if drawing["type"] not in ("f", "fs"):
            continue
        color = _hex(drawing.get("fill"))
        for item in drawing["items"]:
            if item[0] != "re":
                continue
            rect = item[1]
            out.append(
                f'<i style="left:{rect.x0:.4f}pt;top:{rect.y0:.4f}pt;'
                f"width:{rect.width:.4f}pt;height:{rect.height:.4f}pt;"
                f'background:{color}"></i>'
            )
    return out


_ESCAPES = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}


def _esc(char: str) -> str:
    return _ESCAPES.get(char, char)


def _text(page: pymupdf.Page, report: str, engine: str) -> list[str]:
    out: list[str] = []
    for span in page.get_texttrace():
        if span["type"] != 0 or not span["chars"]:
            continue
        try:
            asset = fonts.asset_for_pdf_font(report, span["font"])
        except KeyError:  # pragma: no cover - a font the manifest never saw
            continue
        family = asset["family"]
        size = span["size"]
        color = _hex(span["color"])
        offset = fonts.baseline_offset(family, size, engine)
        weight = "700" if asset["bold"] else "400"
        # Rotated captions: the PDF's writing direction. (1,0) is horizontal;
        # (0,-1) is the bottom-up vertical the rank / summary labels use.
        dx, dy = span["dir"]
        angle = 0.0
        if abs(dy) > 0.5:
            angle = -90.0 if dy < 0 else 90.0
        elif dx < 0:
            angle = 180.0
        for ucs, _gid, origin, _bbox in span["chars"]:
            char = chr(ucs)
            if not char.strip():
                continue
            x, y = origin
            if angle:
                placement = (
                    f"left:{x:.4f}pt;top:{y:.4f}pt;transform-origin:0 0;"
                    f"transform:rotate({angle:g}deg) translateY({-offset:.4f}pt)"
                )
            else:
                placement = f"left:{x:.4f}pt;top:{y - offset:.4f}pt"
            out.append(
                f'<t style="{placement};'
                f"font-family:'{family}';font-size:{size:.4f}pt;font-weight:{weight};"
                f'color:{color}">{_esc(char)}</t>'
            )
    return out


def build_html(pair, engine: str = "weasyprint") -> str:
    with pymupdf.open(pair.pdf) as doc:
        pages: list[str] = []
        first = doc[0].rect
        for index in range(doc.page_count):
            page = doc[index]
            body = "".join(_fills(page)) + "".join(_text(page, pair.name, engine))
            pages.append(
                f'<div class="pg" style="width:{page.rect.width:.4f}pt;'
                f'height:{page.rect.height:.4f}pt">{body}</div>'
            )
    css = (
        f"@page{{size:{first.width:.4f}pt {first.height:.4f}pt;margin:0}}"
        "html,body{margin:0;padding:0;background:#fff}"
        ".pg{position:relative;overflow:hidden;background:#fff}"
        ".pg+.pg{page-break-before:always}"
        "i,t{position:absolute;display:block}"
        f"t{{line-height:0;white-space:pre;{fonts.SHAPING_RESET}}}"
    )
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{pair.name}</title><style>{css}</style></head><body>"
        + "".join(pages)
        + "</body></html>"
    )


def replay(pair, engine: str = "weasyprint") -> Path:
    OUT_HTML.mkdir(parents=True, exist_ok=True)
    OUT_PDF.mkdir(parents=True, exist_ok=True)
    html = build_html(pair, engine=engine)
    (OUT_HTML / f"{pair.name}.html").write_text(html, encoding="utf-8")
    out_pdf = OUT_PDF / f"{pair.name}.pdf"
    printing.print_pdf(html, out_pdf, engine=engine)
    return out_pdf


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="substring of a report name")
    parser.add_argument(
        "--engine", default="weasyprint", choices=list(printing.ENGINES),
        help="which PDF engine to replay through",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT / "tools"))
    from fidelity_gate import compare_report

    worst = 100.0
    for pair in sources.select(args.only):
        out_pdf = replay(pair, engine=args.engine)
        result = compare_report(pair.name, pair.pdf, out_pdf)
        if result.hard_fail:
            print(f"{pair.name}: HARD FAIL {result.hard_fail}")
            worst = 0.0
            continue
        worst = min(worst, result.worst_visible)
        print(
            f"{pair.name}: replay ceiling — worst page visible "
            f"{result.worst_visible:.4f}% exact {result.worst_exact:.4f}% "
            f"({len(result.pages)} page(s))"
        )
        for page in result.pages:
            print(
                f"      p{page.page:<3d} visible {page.visible_pct:8.4f}%  "
                f"exact {page.exact_pct:8.4f}%  max_delta {page.max_delta}"
            )
    print(f"\nreplay ceiling across the selection = {worst:.4f}% visible")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
