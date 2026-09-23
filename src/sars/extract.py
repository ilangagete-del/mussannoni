"""Recover document structure and styling from the reference PDFs.

The reference PDFs are the ground truth. They draw every table cell as an
explicit filled rectangle, so the grid is *stated* rather than inferred:

* ``pdfplumber`` supplies the cell rectangles -> the logical row/column lattice
  and therefore exact ``rowspan`` / ``colspan``.
* ``PyMuPDF`` supplies text spans with resolved font, size, weight, colour and
  rotation, plus the filled rectangles used for cell shading.

Nothing here mutates the input PDFs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pdfplumber
import pymupdf

from .classify import peel_banner_rows, split_tables
from .model import Block, Cell, Document, Line, Page, Style, Table, TextLine

#: Tolerance (pt) for snapping nearly-identical cell edges onto one lattice line.
EDGE_TOL = 1.2

# ---------------------------------------------------------------------------
# font mapping
# ---------------------------------------------------------------------------

_SERIF_HINTS = ("times", "georgia", "book", "roman", "serif")
_NARROW_HINTS = ("narrow", "condensed")
_MONO_HINTS = ("courier", "mono", "consol")

_FALLBACK = "Arial, Helvetica, sans-serif"


def css_family(pdf_font: str) -> str:
    """Map a PDF font name onto a CSS font stack.

    Subset fonts (``CIDFont+F2``, ``BCDEEE+Tahoma-Bold``) carry no reliable
    family, so they fall back to the Arial stack these reports are typeset in.
    """
    name = (pdf_font or "").lower()
    if "+" in name:
        name = name.split("+", 1)[1]
    if name.startswith("cidfont"):
        return _FALLBACK
    if any(h in name for h in _MONO_HINTS):
        return '"Courier New", Courier, monospace'
    if any(h in name for h in _SERIF_HINTS):
        return '"Times New Roman", Times, serif'
    if any(h in name for h in _NARROW_HINTS):
        return '"Arial Narrow", Arial, Helvetica, sans-serif'
    if "tahoma" in name:
        return "Tahoma, Geneva, sans-serif"
    if "verdana" in name:
        return "Verdana, Geneva, sans-serif"
    if "calibri" in name:
        return "Calibri, Candara, Arial, sans-serif"
    if "arial" in name or "helvetica" in name:
        return _FALLBACK
    return _FALLBACK


def int_to_hex(color: int) -> str:
    return f"#{color & 0xFFFFFF:06x}"


# ---------------------------------------------------------------------------
# raw page harvesting
# ---------------------------------------------------------------------------


@dataclass
class Span:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    family: str
    size: float
    bold: bool
    italic: bool
    color: str
    rotation: int

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass
class Fill:
    x0: float
    y0: float
    x1: float
    y1: float
    color: str

    @property
    def area(self) -> float:
        return max(self.x1 - self.x0, 0) * max(self.y1 - self.y0, 0)


def _rotation_of(direction) -> int:
    try:
        dx, dy = float(direction[0]), float(direction[1])
    except Exception:
        return 0
    if abs(dy) > 0.7:
        return 90 if dy < 0 else 270
    return 0 if dx >= 0 else 180


def harvest_spans(page: pymupdf.Page) -> list[Span]:
    spans: list[Span] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            rot = _rotation_of(line.get("dir", (1, 0)))
            for sp in line.get("spans", []):
                text = sp.get("text", "")
                if not text.strip():
                    continue
                x0, y0, x1, y1 = sp["bbox"]
                flags = int(sp.get("flags", 0))
                spans.append(
                    Span(
                        text=text,
                        x0=float(x0),
                        x1=float(x1),
                        top=float(y0),
                        bottom=float(y1),
                        family=css_family(sp.get("font", "")),
                        size=float(sp.get("size", 7.0)),
                        bold=bool(flags & 16),
                        italic=bool(flags & 2),
                        color=int_to_hex(int(sp.get("color", 0))),
                        rotation=rot,
                    )
                )
    return spans


def detect_panel(
    fills: list[Fill], page_w: float, page_h: float
) -> tuple[tuple[float, float, float, float, str] | None, set[int]]:
    """Find a coloured content panel drawn *around* the tables.

    The school result slip washes its content area in cyan, but does so as a
    ring of rectangles that tile the space left over around each table. Such a
    group is recognised by a large union bounding box whose combined area is
    much smaller than that box — a frame, not a solid block (a solid block is a
    cell background and must stay one). The rectangles forming the panel are
    returned so they are not also applied as individual cell shading.
    """
    page_area = page_w * page_h
    if page_area <= 0:
        return None, set()

    by_colour: dict[str, list[Fill]] = {}
    for f in fills:
        by_colour.setdefault(f.color, []).append(f)

    best: tuple[float, float, float, float, str] | None = None
    best_ids: set[int] = set()
    best_union = 0.0

    for colour, group in by_colour.items():
        if len(group) < 3 or colour in ("#ffffff", "#fefefe"):
            continue
        # Near-black rectangles are the table rules themselves: they also form a
        # large, sparse frame, but they are never a background wash.
        if sum(int(colour[i : i + 2], 16) for i in (1, 3, 5)) < 90:
            continue
        x0 = min(f.x0 for f in group)
        y0 = min(f.y0 for f in group)
        x1 = max(f.x1 for f in group)
        y1 = max(f.y1 for f in group)
        union = (x1 - x0) * (y1 - y0)
        total = sum(f.area for f in group)
        if union < page_area * 0.40 or union <= 0:
            continue
        if total / union > 0.70:  # solid fill -> a cell background
            continue
        if union > best_union:
            best_union = union
            best = (x0, y0, x1, y1, colour)
            best_ids = {id(f) for f in group}

    return best, best_ids


def _norm_color(color) -> str | None:
    if color is None:
        return None
    try:
        vals = list(color)
    except TypeError:
        vals = [float(color)] * 3
    if len(vals) == 1:
        vals = vals * 3
    if len(vals) < 3:
        return None
    r, g, b = (max(0.0, min(1.0, float(v))) for v in vals[:3])
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def harvest_fills(page: pymupdf.Page) -> tuple[list[Fill], str | None]:
    """Filled rectangles on the page, plus any page-wide background wash.

    A fill that covers essentially the whole page is the page background (the
    school result slip is washed in cyan). It is returned separately so it is
    not mistaken for the shading of every individual cell.
    """
    fills: list[Fill] = []
    page_bg: str | None = None
    page_area = float(page.rect.width) * float(page.rect.height)
    try:
        drawings = page.get_drawings()
    except Exception:
        return fills, None
    for d in drawings:
        col = d.get("fill")
        if col is None:
            continue
        hexcol = _norm_color(col)
        if hexcol is None:
            continue
        r = d.get("rect")
        if r is None:
            continue
        f = Fill(float(r.x0), float(r.y0), float(r.x1), float(r.y1), hexcol)
        if page_area > 0 and f.area >= page_area * 0.85:
            if hexcol not in ("#ffffff", "#fefefe"):
                page_bg = hexcol
            continue
        fills.append(f)
    return fills, page_bg


# ---------------------------------------------------------------------------
# lattice construction
# ---------------------------------------------------------------------------


def cluster_edges(values: list[float], tol: float = EDGE_TOL) -> list[float]:
    """Collapse near-identical coordinates into a sorted lattice of edges."""
    if not values:
        return []
    ordered = sorted(values)
    groups: list[list[float]] = [[ordered[0]]]
    for v in ordered[1:]:
        if v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [sum(g) / len(g) for g in groups]


def snap(value: float, edges: list[float]) -> int:
    """Index of the lattice edge nearest to *value*."""
    best, bi = None, 0
    for i, e in enumerate(edges):
        d = abs(e - value)
        if best is None or d < best:
            best, bi = d, i
    return bi


def _contains(outer, inner, tol: float = 0.6) -> bool:
    return (
        outer[0] - tol <= inner[0]
        and outer[1] - tol <= inner[1]
        and outer[2] + tol >= inner[2]
        and outer[3] + tol >= inner[3]
        and (outer[2] - outer[0]) * (outer[3] - outer[1])
        > (inner[2] - inner[0]) * (inner[3] - inner[1]) + 1.0
    )


def unique_cells(table) -> list[tuple[float, float, float, float]]:
    """Distinct, non-overlapping cell rectangles for *table*.

    ``pdfplumber`` can report both an outer merged rectangle and the finer
    rectangles nested inside it. Keeping both would duplicate the enclosed text
    and corrupt the row/column lattice, so any rectangle that strictly contains
    another is dropped in favour of the finer partition.
    """
    seen: set[tuple[float, float, float, float]] = set()
    boxes: list[tuple[float, float, float, float]] = []
    for row in table.rows:
        for c in row.cells:
            if not c:
                continue
            key = (round(c[0], 2), round(c[1], 2), round(c[2], 2), round(c[3], 2))
            if key in seen:
                continue
            seen.add(key)
            boxes.append((float(c[0]), float(c[1]), float(c[2]), float(c[3])))

    keep = [b for b in boxes if not any(_contains(b, other) for other in boxes if other is not b)]
    keep.sort(key=lambda b: (b[1], b[0]))
    return keep


# ---------------------------------------------------------------------------
# per-cell content and style
# ---------------------------------------------------------------------------


def _pick_background(bbox, fills: list[Fill]) -> str | None:
    x0, y0, x1, y1 = bbox
    cell_area = max(x1 - x0, 0) * max(y1 - y0, 0)
    if cell_area <= 0:
        return None
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    best: Fill | None = None
    for f in fills:
        if not (f.x0 - 0.7 <= cx <= f.x1 + 0.7 and f.y0 - 0.7 <= cy <= f.y1 + 0.7):
            continue
        # A background must plausibly cover the cell, not be a hairline rule.
        if f.area < cell_area * 0.55:
            continue
        if best is None or f.area < best.area:
            best = f
    if best is None:
        return None
    if best.color in ("#ffffff", "#fefefe"):
        return None
    # Near-black large fills are rule artefacts, never shading.
    r = int(best.color[1:3], 16)
    g = int(best.color[3:5], 16)
    b = int(best.color[5:7], 16)
    if r + g + b < 60:
        return None
    return best.color


def _group_lines(spans: list[Span]) -> list[list[Span]]:
    """Group spans sharing a baseline into visual lines."""
    if not spans:
        return []
    ordered = sorted(spans, key=lambda s: (round(s.cy, 1), s.x0))
    lines: list[list[Span]] = [[ordered[0]]]
    for s in ordered[1:]:
        ref = lines[-1][0]
        tol = max(1.5, min(ref.bottom - ref.top, s.bottom - s.top) * 0.6)
        if abs(s.cy - ref.cy) <= tol:
            lines[-1].append(s)
        else:
            lines.append([s])
    return [sorted(ln, key=lambda s: s.x0) for ln in lines]


def _alignment(bbox, lines: list[list[Span]]) -> str:
    x0, _, x1, _ = bbox
    width = x1 - x0
    if width <= 0 or not lines:
        return "center"
    left_gaps, right_gaps, centre_offsets = [], [], []
    for ln in lines:
        lx0 = min(s.x0 for s in ln)
        lx1 = max(s.x1 for s in ln)
        left_gaps.append(lx0 - x0)
        right_gaps.append(x1 - lx1)
        centre_offsets.append(abs(((lx0 + lx1) / 2) - ((x0 + x1) / 2)))
    lg = sum(left_gaps) / len(left_gaps)
    rg = sum(right_gaps) / len(right_gaps)
    co = sum(centre_offsets) / len(centre_offsets)
    # Centred when both margins are similar and the optical centre matches.
    if co <= max(1.6, width * 0.06) and abs(lg - rg) <= max(2.5, width * 0.12):
        return "center"
    return "left" if lg <= rg else "right"


def _dominant_style(bbox, lines: list[list[Span]], background: str | None) -> Style:
    flat = [s for ln in lines for s in ln]
    if not flat:
        return Style(background=background, align="center")
    # weight by glyph count so the visually dominant run wins
    tally: dict[tuple, int] = {}
    for s in flat:
        key = (s.family, round(s.size, 1), s.bold, s.italic, s.color, s.rotation)
        tally[key] = tally.get(key, 0) + max(len(s.text.strip()), 1)
    family, size, bold, italic, color, rotation = max(tally.items(), key=lambda kv: kv[1])[0]
    return Style(
        family=family,
        size_pt=size,
        bold=bold,
        italic=italic,
        color=color,
        background=background,
        align=_alignment(bbox, lines),
        rotation=rotation,
    )


def _spans_in(bbox, spans: list[Span]) -> list[Span]:
    x0, y0, x1, y1 = bbox
    inside = []
    for s in spans:
        if x0 - 0.6 <= s.cx <= x1 + 0.6 and y0 - 0.6 <= s.cy <= y1 + 0.6:
            inside.append(s)
    return inside


def build_table(pl_table, spans: list[Span], fills: list[Fill]) -> tuple[Table, set[int]]:
    """Build a :class:`Table` from a pdfplumber table, consuming matched spans.

    Returns the table plus the set of ``id()`` values of spans it absorbed.
    """
    boxes = unique_cells(pl_table)
    if not boxes:
        return Table([], [], []), set()

    col_edges = cluster_edges([b[0] for b in boxes] + [b[2] for b in boxes])
    row_edges = cluster_edges([b[1] for b in boxes] + [b[3] for b in boxes])

    cells: list[Cell] = []
    used: set[int] = set()
    n_cols = max(len(col_edges) - 1, 1)

    for bbox in boxes:
        c0 = snap(bbox[0], col_edges)
        c1 = snap(bbox[2], col_edges)
        r0 = snap(bbox[1], row_edges)
        r1 = snap(bbox[3], row_edges)
        colspan = max(c1 - c0, 1)
        rowspan = max(r1 - r0, 1)

        inner = [s for s in _spans_in(bbox, spans) if id(s) not in used]
        for s in inner:
            used.add(id(s))
        groups = _group_lines(inner)
        background = _pick_background(bbox, fills)
        style = _dominant_style(bbox, groups, background)

        line_objs: list[Line] = []
        for grp in groups:
            text = " ".join(s.text for s in grp).strip()
            if not text:
                continue
            # each line keeps its own font/size/weight/colour and alignment
            line_style = _dominant_style(bbox, [grp], None)
            line_objs.append(
                Line(
                    text=text,
                    style=line_style,
                    top=min(s.top for s in grp),
                    bottom=max(s.bottom for s in grp),
                )
            )

        cells.append(
            Cell(
                row=r0,
                col=c0,
                rowspan=rowspan,
                colspan=colspan,
                lines=line_objs,
                style=style,
                full_width=(c0 == 0 and colspan >= n_cols),
            )
        )

    cells.sort(key=lambda c: (c.row, c.col))
    return Table(col_edges=col_edges, row_edges=row_edges, cells=cells), used


def extract_document(pdf_path: Path, source_html: Path) -> Document:
    """Recover a full :class:`Document` from one reference PDF."""
    mu = pymupdf.open(pdf_path)
    doc: Document | None = None

    with pdfplumber.open(pdf_path) as pl:
        for idx, pl_page in enumerate(pl.pages):
            mu_page = mu[idx]
            spans = harvest_spans(mu_page)
            fills, page_bg = harvest_fills(mu_page)
            panel, panel_ids = detect_panel(fills, float(pl_page.width), float(pl_page.height))
            cell_fills = [f for f in fills if id(f) not in panel_ids]

            width = float(pl_page.width)
            height = float(pl_page.height)
            if doc is None:
                doc = Document(
                    name=pdf_path.stem,
                    source_html=str(source_html),
                    reference_pdf=str(pdf_path),
                    width=width,
                    height=height,
                )

            page = Page(
                number=idx + 1,
                width=width,
                height=height,
                background=page_bg,
                panel=panel,
            )
            consumed: set[int] = set()

            for pl_table in pl_page.find_tables():
                table, used = build_table(pl_table, spans, cell_fills)
                if not table.cells:
                    continue
                consumed |= used
                for part in split_tables(table):
                    headings, part = peel_banner_rows(part)
                    for ln in headings:
                        page.blocks.append(
                            Block(
                                kind="text",
                                top=ln.top,
                                text=TextLine(
                                    text=ln.text,
                                    style=ln.style,
                                    x0=0.0,
                                    x1=width,
                                    top=ln.top,
                                    bottom=ln.bottom,
                                ),
                            )
                        )
                    if part.cells:
                        page.blocks.append(Block(kind="table", top=part.row_edges[0], table=part))

            # anything the tables did not absorb is free-standing text
            leftover = [s for s in spans if id(s) not in consumed]
            for ln in _group_lines(leftover):
                text = " ".join(s.text for s in ln).strip()
                if not text:
                    continue
                x0 = min(s.x0 for s in ln)
                x1 = max(s.x1 for s in ln)
                top = min(s.top for s in ln)
                bottom = max(s.bottom for s in ln)
                style = _dominant_style((x0, top, x1, bottom), [ln], None)
                # free text keeps its own horizontal placement
                style = Style(
                    family=style.family,
                    size_pt=style.size_pt,
                    bold=style.bold,
                    italic=style.italic,
                    color=style.color,
                    background=None,
                    align="center" if abs(((x0 + x1) / 2) - width / 2) < width * 0.08 else "left",
                    rotation=style.rotation,
                )
                page.blocks.append(
                    Block(
                        kind="text",
                        top=top,
                        text=TextLine(text=text, style=style, x0=x0, x1=x1, top=top, bottom=bottom),
                    )
                )

            page.blocks.sort(key=lambda b: b.top)
            doc.pages.append(page)

    mu.close()
    assert doc is not None, f"no pages found in {pdf_path}"
    return doc
