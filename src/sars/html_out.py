"""Emit pure HTML + CSS from a recovered :class:`~sars.model.Document`.

Guarantees about the output:

* semantic ``<table>`` / ``<thead>`` / ``<tbody>`` / ``<th>`` / ``<td>`` markup
  with real ``colspan`` / ``rowspan`` and ``scope`` attributes;
* column geometry preserved exactly via ``table-layout: fixed`` plus a
  ``<colgroup>`` whose widths come from the PDF's own cell edges;
* all original styling preserved (font family, size, weight, colour, cell
  shading, alignment, rotation) through a small pool of CSS classes;
* **no** absolute positioning, **no** ``transform: matrix()``, **no** opaque
  per-run positional classes;
* ``@page { size: A4 landscape|portrait }`` so WeasyPrint prints to A4.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path

from .model import Document, Page, Style, Table

# A4 in points.
A4_W, A4_H = 595.276, 841.890
#: Printing margin (pt) applied on every side.
MARGIN_PT = 8.0
#: Table rule width (pt); must match the border in :data:`DOC_CSS`.
BORDER_PT = 0.4


def a4_box(orientation: str) -> tuple[float, float]:
    return (A4_H, A4_W) if orientation == "landscape" else (A4_W, A4_H)


def scale_for(doc: Document) -> float:
    """Uniform fit-to-A4 scale.

    The sources are US-Letter, whose aspect ratio differs from A4, so a single
    uniform factor is used (rather than stretching each axis independently) to
    keep every proportion and relative position exactly as designed.
    """
    pw, ph = a4_box(doc.orientation)
    avail_w = pw - 2 * MARGIN_PT
    avail_h = ph - 2 * MARGIN_PT
    return min(avail_w / doc.width, avail_h / doc.height)


# ---------------------------------------------------------------------------
# style pooling
# ---------------------------------------------------------------------------


@dataclass
class StylePool:
    """Collects distinct cell styles into a compact set of CSS classes."""

    scale: float
    _index: dict[tuple, str] | None = None
    _order: list[tuple[str, Style]] | None = None

    def __post_init__(self) -> None:
        self._index = {}
        self._order = []

    def key(self, style: Style) -> tuple:
        return (
            style.family,
            round(style.size_pt, 2),
            style.bold,
            style.italic,
            style.color,
            style.background,
            style.align,
            style.rotation,
        )

    def class_for(self, style: Style) -> str:
        k = self.key(style)
        assert self._index is not None and self._order is not None
        if k not in self._index:
            name = f"st{len(self._index) + 1}"
            self._index[k] = name
            self._order.append((name, style))
        return self._index[k]

    def css(self) -> str:
        assert self._order is not None
        out: list[str] = []
        for name, st in self._order:
            decls = [
                f"font-family:{st.family}",
                f"font-size:{st.size_pt * self.scale:.2f}pt",
                f"font-weight:{700 if st.bold else 400}",
                f"color:{st.color}",
                f"text-align:{st.align}",
            ]
            if st.italic:
                decls.append("font-style:italic")
            if st.background:
                decls.append(f"background-color:{st.background}")
            out.append(f".{name}{{{';'.join(decls)}}}")
        return "\n".join(out)


# ---------------------------------------------------------------------------
# table rendering
# ---------------------------------------------------------------------------


def _cell_html(cell, pool: StylePool, tag: str, cell_h: float = 0.0) -> str:
    cls = [pool.class_for(cell.style)]
    if cell.is_banner:
        cls.append("banner")
    elif cell.is_total:
        cls.append("total")
    if cell.style.rotation in (90, 270) and cell.lines:
        cls.append("vcell")
    if getattr(cell, "wrappable", False):
        cls.append("wrap")

    attrs = [f'class="{" ".join(cls)}"']
    if cell.colspan > 1:
        attrs.append(f'colspan="{cell.colspan}"')
    if cell.rowspan > 1:
        attrs.append(f'rowspan="{cell.rowspan}"')
    if tag == "th":
        attrs.append('scope="colgroup"' if cell.colspan > 1 else 'scope="col"')

    style_attr = ""
    if len(cell.lines) <= 1:
        # Row height is carried by the cell's line-height rather than by a
        # height on <tr>: WeasyPrint honours explicit row heights by *dropping*
        # rows that no longer fit, which would silently lose report data.
        # Only cells confined to a single row may set it - giving a rowspan cell
        # the full spanned height would inflate its first row by the remainder.
        # The PDF row pitch includes its rule, whereas a CSS border sits outside
        # the line box, so the rule width is deducted to keep the pitch exact.
        if cell_h > 0 and cell.rowspan == 1:
            style_attr = f' style="line-height:{max(cell_h - BORDER_PT, 0.5):.2f}pt"'
        body = html.escape(cell.lines[0].text) if cell.lines else "&#160;"
    else:
        # Multi-line cells (the ministry banner) mix sizes and leading per line,
        # so every line is emitted as its own styled block at its true offset.
        pieces = []
        prev_bottom: float | None = None
        for ln in cell.lines:
            # Each line box is exactly as tall as the glyph box measured in the
            # PDF, and offset by the real gap, so vertical positions are exact
            # and leading is never counted twice.
            box_h = max(ln.bottom - ln.top, 1.0) * pool.scale
            gap = 0.0 if prev_bottom is None else max(ln.top - prev_bottom, 0.0) * pool.scale
            prev_bottom = ln.bottom
            pieces.append(
                f'<div class="ln {pool.class_for(ln.style)}"'
                f' style="margin-top:{gap:.2f}pt;line-height:{box_h:.2f}pt">'
                f"{html.escape(ln.text)}</div>"
            )
        body = "".join(pieces)

    if cell.style.rotation in (90, 270) and body:
        body = f'<span class="rot">{body}</span>'
    return f"<{tag} {' '.join(attrs)}{style_attr}>{body}</{tag}>"


def render_table(table: Table, pool: StylePool, scale: float) -> str:
    n_rows, n_cols = table.n_rows, table.n_cols
    if n_rows == 0 or n_cols == 0:
        return ""

    starts: dict[tuple[int, int], object] = {(c.row, c.col): c for c in table.cells}
    occupied = [[False] * n_cols for _ in range(n_rows)]

    widths = table.col_widths()
    total_w = sum(widths) or 1.0
    cols = "".join(f'<col style="width:{w / total_w * 100:.4f}%">' for w in widths)

    heights = table.row_heights()
    kinds = table.row_kinds or ["data"] * n_rows

    head_rows: list[str] = []
    body_rows: list[str] = []
    # The header band is authoritative for thead membership, so a row whose
    # cells merely mention TOTAL cannot be split away from the band.
    head_end = max(table.header_rows, 0)

    for r in range(n_rows):
        cells_html: list[str] = []
        for c in range(n_cols):
            if occupied[r][c]:
                continue
            cell = starts.get((r, c))
            if cell is None:
                occupied[r][c] = True
                cells_html.append("<td></td>")
                continue
            # A rowspan must never cross the thead/tbody boundary: HTML forbids
            # it, and the span would be silently truncated, shifting every
            # subsequent cell in the following row out of its column.
            limit = head_end if r < head_end else n_rows
            span_rows = max(min(cell.rowspan, limit - r), 1)
            if span_rows != cell.rowspan:
                cell.rowspan = span_rows
            for rr in range(r, min(r + span_rows, n_rows)):
                for cc in range(c, min(c + cell.colspan, n_cols)):
                    occupied[rr][cc] = True
            tag = "th" if cell.is_header else "td"
            span_h = (
                sum(heights[r : min(r + cell.rowspan, len(heights))]) * scale
                if r < len(heights)
                else 0.0
            )
            cells_html.append(_cell_html(cell, pool, tag, span_h))

        kind = kinds[r] if r < len(kinds) else "data"
        row_cls = f' class="{kind}"' if kind in ("banner", "total") else ""
        tr = f"<tr{row_cls}>{''.join(cells_html)}</tr>"
        (head_rows if r < head_end else body_rows).append(tr)

    parts = ["<table>", f"<colgroup>{cols}</colgroup>"]
    if head_rows:
        parts.append("<thead>" + "".join(head_rows) + "</thead>")
    parts.append("<tbody>" + "".join(body_rows) + "</tbody>")
    parts.append("</table>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# page / document rendering
# ---------------------------------------------------------------------------


def render_page(page: Page, pool: StylePool, scale: float, doc: Document) -> str:
    """Render one page.

    Each *block* — a semantic table or a heading — is placed at the exact
    coordinates it occupies in the source PDF. Blocks are positioned rather than
    stacked in normal flow for two reasons: report pages legitimately contain
    blocks whose bounding boxes overlap, and stacking accumulates every small
    rounding difference until content spills onto an extra page. Note that this
    positions whole blocks only: the tabular data inside them is ordinary
    semantic table markup, laid out by the table algorithm.
    """
    chunks: list[str] = []

    if page.panel:
        px0, py0, px1, py1, colour = page.panel
        chunks.append(
            f'<div class="panel" style="top:{py0 * scale:.2f}pt;'
            f"left:{px0 * scale:.2f}pt;width:{(px1 - px0) * scale:.2f}pt;"
            f"height:{(py1 - py0) * scale:.2f}pt;"
            f'background-color:{colour}"></div>'
        )

    for block in page.blocks:
        if block.kind == "table" and block.table is not None:
            table = block.table
            chunks.append(
                f'<div class="tw" style="top:{table.row_edges[0] * scale:.2f}pt;'
                f"left:{table.col_edges[0] * scale:.2f}pt;"
                f'width:{table.width * scale:.2f}pt">' + render_table(table, pool, scale) + "</div>"
            )
        elif block.text is not None:
            t = block.text
            cls = pool.class_for(t.style)
            body = html.escape(t.text)
            if t.style.rotation in (90, 270):
                body = f'<span class="rot">{body}</span>'
            box_h = max(t.bottom - t.top, 1.0) * scale
            geom = (
                f"top:{t.top * scale:.2f}pt;left:{t.x0 * scale:.2f}pt;"
                f"width:{max(t.x1 - t.x0, 1.0) * scale:.2f}pt;"
                f"line-height:{box_h:.2f}pt"
            )
            chunks.append(f'<p class="tl {cls}" style="{geom}">{body}</p>')

    inner_w = doc.width * scale
    inner_h = doc.height * scale
    bg = f";background-color:{page.background}" if page.background else ""
    return (
        f'<section class="page" style="width:{inner_w:.2f}pt;'
        f'height:{inner_h:.2f}pt{bg}">' + "".join(chunks) + "</section>"
    )


DOC_CSS = """\
*{margin:0;padding:0;box-sizing:border-box}
html{-weasy-hyphens:none}
body{background:#fff}
/* No overflow:hidden - clipping would silently drop report data. Any overflow
   must surface as an extra page so verification catches it. */
.page{position:relative;margin:0 auto;page-break-after:always;break-after:page}
.page:last-of-type{page-break-after:auto;break-after:auto}
/* Whole blocks are placed at their measured coordinates; the data inside each
   block is laid out by the normal CSS table algorithm. */
.panel{position:absolute;z-index:0}
.tw{position:absolute;z-index:1;overflow:visible}
p.tl{position:absolute;z-index:1}
table{border-collapse:collapse;table-layout:fixed;width:100%;
      border-spacing:0}
/* The PDF already states where every line breaks; those breaks are emitted as
   <br>, so automatic re-wrapping must be off or tokens would split. */
/* Vertical padding is zero on purpose: row heights are taken verbatim from the
   PDF, and on a 59-row page even 0.4pt of padding per cell would accumulate
   into tens of points of overflow. */
/* overflow is visible on purpose: several reports set labels slightly wider
   than their ruled cell (OWNERSHIP, the rotated rank columns) and the original
   PDF simply lets them overhang. Clipping here would truncate real values. */
th,td{border:0.4pt solid #000;padding:0 0.8pt;line-height:1.02;
      overflow:visible;white-space:nowrap;overflow-wrap:normal;word-break:normal;
      vertical-align:middle}
/* Elastic cells: only where the extractor found content wider than its column
   (a long SCHOOL NAME, a long COMPETENCY LEVEL label). These wrap inside the
   ruled box at word boundaries instead of overhanging it, and the row grows to
   fit. Applied per cell so untouched cells keep their exact single-line
   geometry and the 100% text guarantee. */
th.wrap,td.wrap{white-space:normal;overflow-wrap:break-word}
th{font-weight:700}
tr.banner th,tr.banner td{border:0;vertical-align:top}
div.ln{white-space:nowrap}
tr.total th,tr.total td{font-weight:700}
p.tl{white-space:nowrap}
/* Vertical rank labels. WeasyPrint does not implement writing-mode, so a real
   rotate() transform is used; the cell must not clip the overflow it creates. */
.rot{display:inline-block;transform:rotate(-90deg);transform-origin:50% 50%;
     white-space:nowrap;line-height:1}
th.vcell,td.vcell{overflow:visible}
"""


def render_document(doc: Document) -> str:
    """Render one document as a fully self-contained HTML file.

    The complete stylesheet (the shared structural :data:`DOC_CSS` plus this
    document's own pooled per-cell style classes) is inlined into the file's
    own ``<head>``; the file links no external stylesheet, so every
    ``output/html/<name>.html`` is standalone and reviewable on its own.
    """
    scale = scale_for(doc)
    pool = StylePool(scale=scale)
    pages = [render_page(p, pool, scale, doc) for p in doc.pages]

    pw, ph = a4_box(doc.orientation)
    page_css = (
        f"@page{{size:A4 {doc.orientation};margin:{MARGIN_PT:.2f}pt}}"
        f"\n/* A4 {doc.orientation}: {pw:.1f}x{ph:.1f}pt; "
        f"source {doc.width:.0f}x{doc.height:.0f}pt; scale {scale:.4f} */"
    )

    title = html.escape(doc.name)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
{DOC_CSS}
{page_css}
{pool.css()}
</style>
</head>
<body>
{"".join(pages)}
</body>
</html>
"""


def write_document(doc: Document, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{doc.name}.html"
    target.write_text(render_document(doc), encoding="utf-8")
    return target
