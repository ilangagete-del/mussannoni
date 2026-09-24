"""Data model for a recovered report document.

The model is deliberately presentation-complete: every value needed to emit
faithful HTML + CSS (geometry, fonts, colours, alignment, spans) is captured
here, so the emitter never has to guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Style:
    """Resolved visual style of a run of text (and its cell background)."""

    family: str = "Arial, Helvetica, sans-serif"
    size_pt: float = 7.0
    bold: bool = False
    italic: bool = False
    color: str = "#000000"
    background: str | None = None
    align: str = "center"
    #: Text rotation in degrees (0 or 90 for the vertical rank labels).
    rotation: int = 0

    def css(self) -> str:
        parts = [
            f"font-family:{self.family}",
            f"font-size:{self.size_pt:.2f}pt",
            f"color:{self.color}",
            f"text-align:{self.align}",
        ]
        parts.append("font-weight:700" if self.bold else "font-weight:400")
        if self.italic:
            parts.append("font-style:italic")
        if self.background:
            parts.append(f"background-color:{self.background}")
        return ";".join(parts)


@dataclass
class Line:
    """One visual line of text inside a cell, with its own resolved style.

    Multi-line cells (notably the ministry banner) mix font sizes and weights
    per line, so each line carries its own style and vertical placement.
    """

    text: str
    style: Style
    top: float
    bottom: float


@dataclass
class Cell:
    """A single table cell mapped onto the logical row/column lattice."""

    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1
    lines: list[Line] = field(default_factory=list)
    style: Style = field(default_factory=Style)
    is_header: bool = False
    #: True for aggregate rows such as ``TOTAL`` / ``AVERAGE``.
    is_total: bool = False
    #: True for the full-width ministry / region title block.
    is_banner: bool = False
    #: True when this cell spans the full table width (a banner / section title).
    full_width: bool = False
    #: True when the cell's content is wider than its column, so the emitter
    #: should let it wrap inside the box instead of overhanging the rule.
    wrappable: bool = False

    @property
    def text(self) -> str:
        return " ".join(ln.text for ln in self.lines).strip()

    @property
    def is_empty(self) -> bool:
        return not self.text

    @property
    def leading(self) -> float:
        """Average baseline-to-baseline distance of this cell's lines."""
        if len(self.lines) < 2:
            return 0.0
        first, last = self.lines[0], self.lines[-1]
        return (last.top - first.top) / (len(self.lines) - 1)


@dataclass
class Table:
    """A table recovered from the PDF's own drawn cell rectangles."""

    col_edges: list[float]
    row_edges: list[float]
    cells: list[Cell]
    #: Number of leading lattice rows that constitute the header band.
    header_rows: int = 0
    #: Lattice rows (from the end) that constitute a totals / summary band.
    footer_rows: int = 0
    #: Per-row role: ``banner`` | ``header`` | ``data`` | ``total``.
    row_kinds: list[str] = field(default_factory=list)

    @property
    def n_cols(self) -> int:
        return max(len(self.col_edges) - 1, 0)

    @property
    def n_rows(self) -> int:
        return max(len(self.row_edges) - 1, 0)

    @property
    def width(self) -> float:
        return self.col_edges[-1] - self.col_edges[0] if self.col_edges else 0.0

    def col_widths(self) -> list[float]:
        return [self.col_edges[i + 1] - self.col_edges[i] for i in range(len(self.col_edges) - 1)]

    def row_heights(self) -> list[float]:
        return [self.row_edges[i + 1] - self.row_edges[i] for i in range(len(self.row_edges) - 1)]


@dataclass
class TextLine:
    """A line of text that lives outside any table."""

    text: str
    style: Style
    x0: float
    x1: float
    top: float
    bottom: float


@dataclass
class Block:
    """Ordered page content: either a table or a free text line."""

    kind: str  # "table" | "text"
    top: float
    table: Table | None = None
    text: TextLine | None = None


@dataclass
class Page:
    number: int
    width: float
    height: float
    blocks: list[Block] = field(default_factory=list)
    #: Page-wide background wash (e.g. the cyan of the school result slip).
    background: str | None = None
    #: Coloured content panel behind the tables: ``(x0, y0, x1, y1, colour)``.
    panel: tuple[float, float, float, float, str] | None = None


@dataclass
class Document:
    name: str
    source_html: str
    reference_pdf: str
    width: float
    height: float
    pages: list[Page] = field(default_factory=list)

    @property
    def orientation(self) -> str:
        return "landscape" if self.width > self.height else "portrait"
