"""Domain classification for Mwanza school-results tables.

These reports aggregate Form Two mock assessment results up a fixed hierarchy —
*school -> ward -> council -> region* — which makes the role of each row and
column unambiguous. That domain knowledge is used here to label:

* **banner** rows  - the ministry / region title block spanning the full width;
* **header** rows  - the grouped column headings (``NUMBER OF CANDIDATES`` ->
  ``REGISTERED`` / ``SAT`` -> ``F`` / ``M`` / ``T``);
* **total** rows   - ``TOTAL`` / ``AVERAGE`` aggregate lines;
* **data** rows    - one school, ward, council, subject or candidate each.
"""

from __future__ import annotations

import re

from .model import Table

#: Column headings that appear in these reports (upper-cased, punctuation free).
HEADER_TERMS: frozenset[str] = frozenset(
    {
        "S/NO",
        "SNO",
        "NO",
        "SCHOOL NAME",
        "SCHOOL",
        "CENTRE",
        "CENTRE NAME",
        "WARD",
        "WARD NAME",
        "COUNCIL",
        "COUNCIL NAME",
        "DISTRICT",
        "REGION",
        "OWNERSHIP",
        "CATEGORY",
        "NUMBER OF CANDIDATES",
        "REGISTERED",
        "SAT",
        "ABSENT",
        "DIVISION PERFORMANCE",
        "DIVISION",
        "DIV",
        "GPA",
        "COMPETENCY LEVEL",
        "COMPETENCY",
        "RANK",
        "C/RANK",
        "R/RANK",
        "W/RANK",
        "POSITION",
        "POS",
        "CNO",
        "CANDIDATE FULL NAME",
        "CANDIDATE NAME",
        "NAME",
        "SEX",
        "AGGT",
        "AGGREGATE",
        "POINTS",
        "DETAILED SUBJECTS",
        "SUBJECTS",
        "SUBJECT",
        "SUBJECT NAME",
        "CODE",
        "AVERAGE",
        "GRADE",
        "PASSED",
        "FAILED",
        "PERFORMANCE",
        "I",
        "II",
        "III",
        "IV",
        "0",
        "I-III",
        "I-IV",
        "F",
        "M",
        "T",
        "%",
        "A",
        "B",
        "C",
        "D",
        "E",
    }
)

#: Row labels that mark an aggregate line.
TOTAL_TERMS: frozenset[str] = frozenset(
    {
        "TOTAL",
        "GRAND TOTAL",
        "TOTALS",
        "REGION TOTAL",
        "COUNCIL TOTAL",
        "WARD TOTAL",
        "SUM",
        "AVERAGE",
        "AVERAGES",
        "MEAN",
        "OVERALL",
    }
)

#: A candidate/centre index such as ``1``, ``12.`` or ``S1051-0001``.
_ORDINAL = re.compile(r"^\d{1,4}\.?$")
_CAND_ID = re.compile(r"^[A-Z]{1,2}\d{3,6}([-/]\d{1,5})?$", re.IGNORECASE)
_NUMERIC = re.compile(r"^-?[\d,]+(\.\d+)?%?$")


def _norm(text: str) -> str:
    return re.sub(r"[.\s]+", " ", text.upper()).strip().rstrip(".").strip()


def is_header_text(text: str) -> bool:
    return _norm(text) in HEADER_TERMS


def is_total_text(text: str) -> bool:
    return _norm(text) in TOTAL_TERMS


def is_numeric(text: str) -> bool:
    return bool(_NUMERIC.match(text.strip()))


def _rows_map(table: Table) -> dict[int, list]:
    rows: dict[int, list] = {}
    for cell in table.cells:
        rows.setdefault(cell.row, []).append(cell)
    return rows


def _is_banner_row(cells: list, n_cols: int) -> bool:
    filled = [c for c in cells if not c.is_empty]
    if len(filled) != 1:
        return False
    only = filled[0]
    return only.col == 0 and only.colspan >= max(n_cols - 1, 1)


def _is_data_row(cells: list) -> bool:
    """A data row starts with an index/ID, or is mostly numeric measurements."""
    filled = sorted((c for c in cells if not c.is_empty), key=lambda c: c.col)
    if not filled:
        return False
    lead = filled[0]
    if lead.col <= 1 and (_ORDINAL.match(lead.text.strip()) or _CAND_ID.match(lead.text.strip())):
        return True
    if is_total_text(lead.text):
        return False
    numeric = sum(1 for c in filled if is_numeric(c.text))
    # Headers are label bands; data rows carry a solid majority of figures.
    return len(filled) >= 4 and numeric >= max(3, int(len(filled) * 0.5))


def classify(table: Table) -> Table:
    """Annotate *table* with row kinds, header flags and header/footer counts."""
    rows = _rows_map(table)
    if not rows:
        return table

    n_rows = table.n_rows or (max(rows) + 1)
    n_cols = table.n_cols or 1
    kinds: list[str] = []

    first_data: int | None = None
    for r in range(n_rows):
        cells = rows.get(r, [])
        if _is_banner_row(cells, n_cols):
            kinds.append("banner")
            continue
        if _is_data_row(cells):
            kinds.append("data")
            if first_data is None:
                first_data = r
            continue
        # A row may only be an aggregate once real data has started. Before that
        # we are still in the header band, where a column *headed* ``TOTAL`` is
        # commonplace and must not be mistaken for a totals row.
        if (
            first_data is not None
            and cells
            and any(is_total_text(c.text) for c in cells if not c.is_empty)
        ):
            kinds.append("total")
            continue
        kinds.append("header" if first_data is None else "data")

    # Everything before the first genuine data row belongs to the header band.
    if first_data is None:
        first_data = n_rows
    for r in range(first_data):
        if kinds[r] == "data":
            kinds[r] = "header"

    table.row_kinds = kinds
    table.header_rows = first_data
    table.footer_rows = 0

    for cell in table.cells:
        kind = kinds[cell.row] if cell.row < len(kinds) else "data"
        cell.is_header = kind in ("header", "banner")
        cell.is_total = kind == "total"
        cell.is_banner = kind == "banner"

    merge_header_stacks(table)
    trim_trailing_empty_rows(table)
    return table


def trim_trailing_empty_rows(table: Table) -> Table:
    """Drop blank lattice rows at the foot of a table.

    The PDFs often close a table with a ruled but empty strip; carried over
    literally it renders as a stray empty row under the last record.
    """
    if not table.cells or table.n_rows == 0:
        return table

    last_used = -1
    for cell in table.cells:
        if not cell.is_empty:
            last_used = max(last_used, cell.row + cell.rowspan - 1)
    if last_used < 0 or last_used >= table.n_rows - 1:
        return table

    keep_rows = last_used + 1
    table.cells = [c for c in table.cells if c.row < keep_rows]
    for cell in table.cells:
        cell.rowspan = min(cell.rowspan, keep_rows - cell.row)
    table.row_edges = table.row_edges[: keep_rows + 1]
    if table.row_kinds:
        table.row_kinds = table.row_kinds[:keep_rows]
    table.header_rows = min(table.header_rows, keep_rows)
    return table


def merge_header_stacks(table: Table) -> Table:
    """Collapse stacked single-column header cells into one tall cell.

    Columns that apply to the whole header band — ``GPA``, ``COMPETENCY LEVEL``,
    ``RANK`` — are drawn in the PDF as a stack of rectangles with the label in
    just one of them. Semantically that is a single heading spanning the band, so
    the run is merged into one cell carrying the label and the correct
    ``rowspan``.
    """
    band = table.header_rows
    if band < 2:
        return table

    by_pos = {(c.row, c.col): c for c in table.cells}
    drop: set[int] = set()

    for col in range(table.n_cols):
        row = 0
        while row < band:
            run: list = []
            r = row
            while r < band:
                cell = by_pos.get((r, col))
                if cell is None or cell.colspan != 1 or cell.rowspan != 1 or cell.is_banner:
                    break
                run.append(cell)
                r += 1
            if len(run) > 1:
                filled = [c for c in run if not c.is_empty]
                if len(filled) <= 1:
                    keeper = filled[0] if filled else run[0]
                    keeper.row = run[0].row
                    keeper.rowspan = len(run)
                    for other in run:
                        if other is not keeper:
                            drop.add(id(other))
                row = r if r > row else row + 1
            else:
                row = r + 1 if r == row else r

    if drop:
        table.cells = [c for c in table.cells if id(c) not in drop]
        table.cells.sort(key=lambda c: (c.row, c.col))
    return table


def _blank_rows(table: Table) -> set[int]:
    """Lattice rows crossed by no text at all."""
    used: set[int] = set()
    for cell in table.cells:
        if cell.is_empty:
            continue
        for r in range(cell.row, cell.row + cell.rowspan):
            used.add(r)
    return {r for r in range(table.n_rows) if r not in used}


def _compact_columns(cells: list, col_edges: list[float]) -> tuple[list, list[float]]:
    """Drop columns that carry no text, renumbering the survivors."""
    keep: set[int] = set()
    for cell in cells:
        if cell.is_empty:
            continue
        for c in range(cell.col, cell.col + cell.colspan):
            keep.add(c)
    if not keep:
        return cells, col_edges

    lo, hi = min(keep), max(keep)
    # Keep the contiguous span actually in use, so interior blank columns that
    # belong to the table (empty division counts) are preserved.
    kept = list(range(lo, hi + 1))
    remap = {old: new for new, old in enumerate(kept)}

    out = []
    for cell in cells:
        start = max(cell.col, lo)
        end = min(cell.col + cell.colspan - 1, hi)
        if end < start:
            continue
        cell.col = remap[start]
        cell.colspan = remap[end] - remap[start] + 1
        out.append(cell)
    return out, col_edges[lo : hi + 2]


def split_tables(table: Table) -> list[Table]:
    """Split a detected table at blank row bands into independent tables.

    ``pdfplumber`` reports one lattice per contiguous region of ruled cells, so
    a page holding a small summary pivot above a large results table comes back
    merged. Their columns do not line up, which leaves stray empty cells around
    each. Splitting on blank row bands — then recomputing each part's own column
    range — restores the two tables the report actually contains.
    """
    if table.n_rows == 0 or not table.cells:
        return [table]

    blanks = _blank_rows(table)
    groups: list[list[int]] = []
    current: list[int] = []
    for r in range(table.n_rows):
        if r in blanks:
            if current:
                groups.append(current)
                current = []
            continue
        current.append(r)
    if current:
        groups.append(current)

    if len(groups) <= 1:
        return [table]

    parts: list[Table] = []
    for rows in groups:
        lo, hi = rows[0], rows[-1]
        cells = []
        for cell in table.cells:
            if cell.row < lo or cell.row > hi:
                continue
            cell.row -= lo
            cell.rowspan = min(cell.rowspan, hi - lo + 1 - cell.row)
            cells.append(cell)
        if not cells:
            continue
        cells, edges = _compact_columns(cells, table.col_edges)
        parts.append(
            Table(
                col_edges=edges,
                row_edges=table.row_edges[lo : hi + 2],
                cells=sorted(cells, key=lambda c: (c.row, c.col)),
            )
        )
    return parts or [table]


def peel_banner_rows(table: Table) -> tuple[list, Table]:
    """Lift full-width title rows out of *table*.

    A ministry banner or a section title such as
    ``TOP TEN BEST GOVERNMENT SCHOOLS DISTRICTWISE`` is drawn as a cell spanning
    every column. It is a document heading, not tabular data, and keeping it
    inside the table forces the table to the full page width — which prevents a
    narrow summary pivot from sizing to its own content. The peeled rows are
    returned as free lines, and the remaining table is re-compacted.
    """
    if not table.cells or table.n_rows == 0:
        return [], table

    by_row: dict[int, list] = {}
    for cell in table.cells:
        by_row.setdefault(cell.row, []).append(cell)

    n_cols = table.n_cols or 1
    peeled: list = []
    first_kept = 0
    for r in range(table.n_rows):
        cells = by_row.get(r, [])
        filled = [c for c in cells if not c.is_empty]
        if len(filled) != 1:
            break
        only = filled[0]
        if only.col != 0 or only.colspan < max(n_cols - 1, 1):
            break
        peeled.extend(only.lines)
        first_kept = r + 1

    if not peeled:
        return [], table

    kept = []
    for cell in table.cells:
        if cell.row < first_kept:
            continue
        cell.row -= first_kept
        kept.append(cell)
    if not kept:
        return peeled, Table([], [], [])

    cells, edges = _compact_columns(kept, table.col_edges)
    return peeled, Table(
        col_edges=edges,
        row_edges=table.row_edges[first_kept:],
        cells=sorted(cells, key=lambda c: (c.row, c.col)),
    )
