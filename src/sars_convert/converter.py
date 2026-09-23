"""Convert pdf2html fixed-layout HTML into clean semantic HTML+CSS.

This module implements a *prototype* geometry-based table-reconstruction
converter used for the FEAT-002 evidence-based decision checkpoint.

Per the FEAT-002 decision (see ``DECISION.md``), the batch is converted
**per file / per template** rather than by a single generic detector: a naive
page-wide geometric model over-fragments the S1051 page (title block + summary
pivot + results table) into misaligned column bands. This module is therefore
retained as a tested geometry **assist/scaffold** — its :func:`parse_matrix`,
:func:`parse_runs`, :func:`parse_font_classes`, :func:`parse_page_size` and
:func:`cluster_rows` helpers are the reliable substrate the per-template
builders in FEAT-003 build on (row clustering is trustworthy; page-wide column
clustering is not).

The pdf2html source encodes every glyph run as an absolutely-positioned
``<div class="t cN">`` whose on-page position is carried by
``transform:matrix(a,b,c,d,X,Y)`` (X/Y in CSS px) and whose font attributes
come from a pooled ``.cN`` class defined in the document ``<style>``.

The reconstruction strategy is purely geometric:

1. Parse every text run: text, X, Y, rotation flag and resolved font info.
2. Cluster runs into **rows** by Y proximity (a tolerance derived from font
   size / line height).
3. Cluster the row start X positions into **column bands**.
4. Assign each run to a column band and emit a clean semantic ``<table>``.

The helpers (:func:`parse_matrix`, :func:`cluster_rows`,
:func:`cluster_columns`) are deliberately small and side-effect free so they
can be unit-tested on inline fixtures regardless of the eventual
generic-vs-per-file decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape

try:  # pragma: no cover - import shim
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[assignment]


_MATRIX_RE = re.compile(r"matrix\(([^)]+)\)")
_FONT_SIZE_RE = re.compile(r"font-size:\s*([0-9.]+)px")
_FONT_FAMILY_RE = re.compile(r"font-family:\s*([^;]+)")
_FONT_WEIGHT_RE = re.compile(r"font-weight:\s*([^;]+)")
_COLOR_RE = re.compile(r"color:\s*([^;]+)")
_PAGE_SIZE_RE = re.compile(r"@page\s*\{[^}]*size:\s*([0-9.]+)px\s+([0-9.]+)px")


@dataclass
class FontInfo:
    """Resolved font attributes for a pooled ``.cN`` class."""

    family: str = "sans-serif"
    size: float = 11.0
    weight: str = "normal"
    color: str = "#000000"


@dataclass
class Run:
    """A single positioned text run parsed from the source HTML."""

    text: str
    x: float
    y: float
    rotated: bool
    font: FontInfo
    css_class: str = ""


@dataclass
class Row:
    """A cluster of runs sharing (approximately) one Y coordinate."""

    y: float
    runs: list[Run] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Geometry helpers (unit-tested)
# ---------------------------------------------------------------------------
def parse_matrix(style: str) -> tuple[float, float, float, float, float, float] | None:
    """Parse ``transform:matrix(a,b,c,d,X,Y)`` from an inline ``style`` string.

    Returns the six matrix components as floats, or ``None`` when no matrix is
    present. X and Y (the translation) are the 5th and 6th components.
    """
    match = _MATRIX_RE.search(style or "")
    if not match:
        return None
    parts = [p.strip() for p in match.group(1).split(",")]
    if len(parts) != 6:
        return None
    try:
        a, b, c, d, x, y = (float(p) for p in parts)
    except ValueError:
        return None
    return a, b, c, d, x, y


def is_rotated(matrix: tuple[float, float, float, float, float, float]) -> bool:
    """A run is rotated/skewed when the off-diagonal matrix terms are non-zero."""
    _, b, c, _, _, _ = matrix
    return abs(b) > 1e-6 or abs(c) > 1e-6


def cluster_rows(runs: list[Run], tolerance: float = 4.0) -> list[Row]:
    """Cluster runs into visual rows by Y proximity.

    Runs whose Y differs by no more than ``tolerance`` px are treated as the
    same row (this absorbs the sub-pixel baseline jitter pdf2html emits, e.g.
    a name run at Y=303.8 alongside its numeric cells at Y=304.4). Each row's
    runs are returned left-to-right by X.
    """
    ordered = sorted(runs, key=lambda r: (r.y, r.x))
    rows: list[Row] = []
    for run in ordered:
        placed = False
        for row in rows:
            if abs(row.y - run.y) <= tolerance:
                row.runs.append(run)
                # Track the mean Y so drift across a wide row stays centred.
                row.y = (row.y * (len(row.runs) - 1) + run.y) / len(row.runs)
                placed = True
                break
        if not placed:
            rows.append(Row(y=run.y, runs=[run]))
    for row in rows:
        row.runs.sort(key=lambda r: r.x)
    rows.sort(key=lambda r: r.y)
    return rows


def cluster_columns(rows: list[Row], tolerance: float = 12.0) -> list[float]:
    """Derive column band start positions from the X of every run.

    All run X starts are pooled and 1-D clustered: X values within
    ``tolerance`` px of an existing band centre join that band. The sorted band
    centres are returned and used as column boundaries.
    """
    xs = sorted(run.x for row in rows for run in row.runs)
    bands: list[list[float]] = []
    for x in xs:
        if bands and x - bands[-1][-1] <= tolerance:
            bands[-1].append(x)
        else:
            bands.append([x])
    return [sum(b) / len(b) for b in bands]


def assign_column(x: float, bands: list[float]) -> int:
    """Return the index of the band whose centre is nearest to ``x``."""
    best, best_dist = 0, float("inf")
    for i, centre in enumerate(bands):
        dist = abs(centre - x)
        if dist < best_dist:
            best, best_dist = i, dist
    return best


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def parse_font_classes(style_text: str) -> dict[str, FontInfo]:
    """Extract ``.cN`` font definitions from the pooled ``<style>`` text."""
    fonts: dict[str, FontInfo] = {}
    for match in re.finditer(r"\.(c\d+)\s*\{([^}]*)\}", style_text):
        name, body = match.group(1), match.group(2)
        info = FontInfo()
        if (m := _FONT_FAMILY_RE.search(body)) is not None:
            info.family = m.group(1).strip()
        if (m := _FONT_SIZE_RE.search(body)) is not None:
            info.size = float(m.group(1))
        if (m := _FONT_WEIGHT_RE.search(body)) is not None:
            info.weight = m.group(1).strip()
        if (m := _COLOR_RE.search(body)) is not None:
            info.color = m.group(1).strip()
        fonts[name] = info
    return fonts


def parse_page_size(style_text: str) -> tuple[float, float] | None:
    """Return the (width, height) px from the ``@page`` rule, if present."""
    match = _PAGE_SIZE_RE.search(style_text)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def parse_runs(page, fonts: dict[str, FontInfo]) -> list[Run]:
    """Parse every ``div.t`` run inside a page element into :class:`Run`."""
    runs: list[Run] = []
    for div in page.select("div.t"):
        matrix = parse_matrix(div.get("style", ""))
        if matrix is None:
            continue
        classes = [c for c in (div.get("class") or []) if c.startswith("c")]
        css_class = classes[0] if classes else ""
        text = div.get_text()
        if not text.strip():
            continue
        runs.append(
            Run(
                text=text,
                x=matrix[4],
                y=matrix[5],
                rotated=is_rotated(matrix),
                font=fonts.get(css_class, FontInfo()),
                css_class=css_class,
            )
        )
    return runs


# ---------------------------------------------------------------------------
# Reconstruction / emit
# ---------------------------------------------------------------------------
def rows_to_table(rows: list[Row], bands: list[float], header_rows: int = 1) -> str:
    """Emit a semantic ``<table>`` from clustered rows and column bands."""
    n_cols = len(bands)
    out = ["<table>"]
    for idx, row in enumerate(rows):
        cells = [""] * n_cols
        for run in row.runs:
            col = assign_column(run.x, bands)
            joiner = " " if cells[col] else ""
            cells[col] = f"{cells[col]}{joiner}{run.text.strip()}"
        tag = "th" if idx < header_rows else "td"
        section_open = ""
        section_close = ""
        if idx == 0:
            section_open = "<thead>"
        if idx == header_rows:
            section_open = "<tbody>"
        if header_rows and idx == header_rows - 1:
            section_close = "</thead>"
        if section_open:
            out.append(section_open)
        tds = "".join(f"<{tag}>{escape(c)}</{tag}>" for c in cells)
        out.append(f"<tr>{tds}</tr>")
        if section_close:
            out.append(section_close)
    if len(rows) <= header_rows:
        out.append("</thead>")
    else:
        out.append("</tbody>")
    out.append("</table>")
    return "\n".join(out)


_CSS = """\
:root { font-family: Arial, Helvetica, sans-serif; }
body { margin: 0; color: #002060; }
table { border-collapse: collapse; width: 100%; font-size: 9.5px; }
th, td { border: 1px solid #99a; padding: 2px 4px; text-align: left; vertical-align: top; }
thead th { background: #dfe3ef; font-weight: 700; }
.page-block { page-break-after: always; padding: 12px; }
h1, h2 { text-align: center; color: #7030a0; margin: 2px 0; }
h1 { font-size: 15px; }
h2 { font-size: 12px; }
"""


def convert(html: str, page_index: int = 0) -> str:
    """Convert a pdf2html HTML string into clean semantic HTML+CSS.

    This prototype reconstructs the largest data table on the requested page.
    It is intentionally simple: the FEAT-002 checkpoint uses it to *judge* how
    faithfully a generic geometry approach reproduces the report, not to be the
    final production pipeline.
    """
    if BeautifulSoup is None:  # pragma: no cover
        raise RuntimeError("beautifulsoup4 is required")
    soup = BeautifulSoup(html, "lxml")
    style_text = " ".join(s.get_text() for s in soup.find_all("style"))
    fonts = parse_font_classes(style_text)
    size = parse_page_size(style_text)

    pages = soup.select("div.page")
    if not pages:
        raise ValueError("no .page elements found")
    page = pages[page_index]
    runs = parse_runs(page, fonts)
    upright = [r for r in runs if not r.rotated]
    rows = cluster_rows(upright)
    bands = cluster_columns(rows)

    body = [f"<style>{_CSS}</style>", '<div class="page-block">']
    if size:
        body.append(f"<!-- source page size {size[0]}x{size[1]} px -->")
    body.append(rows_to_table(rows, bands))
    body.append("</div>")
    return (
        '<!DOCTYPE html>\n<html lang="en-US">\n<head>\n'
        '<meta charset="utf-8">\n' + "\n".join(body) + "\n</body>\n</html>\n"
    )
