"""Schools-rank / top-schools template.

Serves the ``schools_rank`` and ``top_schools`` report types (council and
region level, overall / government / private variants share this structure).
The static chrome - the ``NUMBER OF CANDIDATES`` / ``DIVISION PERFORMANCE``
group headings and their ``REGISTERED`` / ``SAT`` / division sub-columns - lives
here; the per-school figures come from the :class:`~sars.schema.SchoolRankRow`
data.

Expected data shape: a :class:`~sars.schema.SchoolsRankReport` with

* ``meta``   - :class:`~sars.schema.ReportMeta` (``level`` picks council vs
  region identity columns: council rows carry ``ward``, region rows
  ``council``);
* ``rows``   - :class:`~sars.schema.SchoolRankRow` (sno, identity, ownership,
  ``registered`` / ``sat`` :class:`~sars.schema.GenderCounts`, ``sat_pct``, the
  ``division`` map of ``{label: {f,m,t}}`` plus ``<label>%`` percentages, gpa,
  competency, council_rank, regional_rank);
* ``totals`` - ``{label: [cell, ...]}`` for the TOTAL summary row's data.
"""

from __future__ import annotations

from ..schema import CellStyle, PerformanceTable, SchoolRankRow, SchoolsRankReport
from .base import (
    TemplatePool,
    banner_html,
    competency_cell,
    document_html,
    esc,
    orientation_for,
    styled_cell,
)
from .generic import _thead as _generic_thead

#: Division-performance sub-columns in printed order, with which of F/M/T/%
#: each carries. Percentages sit under ``0``, ``I-III`` and ``I-IV``.
_DIVISIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("I", ("f", "m", "t")),
    ("II", ("f", "m", "t")),
    ("III", ("f", "m", "t")),
    ("IV", ("f", "m", "t")),
    ("0", ("f", "m", "t", "%")),
    ("I-III", ("f", "m", "t", "%")),
    ("I-IV", ("f", "m", "t", "%")),
)


def _colgroup(level: str) -> str:
    """Proportional column widths so wide text columns get room and the many
    numeric columns stay narrow - preventing a long SCHOOL NAME from overhanging
    into its neighbour (which the PDF text extractor would merge into one token)
    while still fitting every column on one page."""
    widths: list[float] = [2.0, 5.5, 8.0, 4.0]  # S/NO, ident, school, ownership
    widths += [2.1, 2.1, 2.1, 2.1, 2.1, 2.1, 2.1]  # registered F/M/T + sat F/M/T/%
    div_span = sum(len(sub) for _, sub in _DIVISIONS)
    widths += [1.95] * div_span
    widths += [3.6, 8.5, 2.0, 2.0]  # gpa, competency, c/rank, r/rank
    total = sum(widths)
    cols = "".join(f'<col style="width:{w / total * 100:.4f}%">' for w in widths)
    return f"<colgroup>{cols}</colgroup>"


def _thead(level: str) -> str:
    """The three-row grouped header band (chrome)."""
    ident = "WARD" if level == "council" else "COUNCIL"
    # Row 1: identity columns (rowspan 3) + the two big group headings + GPA
    #        block + competency + rank columns.
    div_span = sum(len(sub) for _, sub in _DIVISIONS)
    r1 = (
        '<th rowspan="3" class="nw">S/NO.</th>'
        f'<th rowspan="3" class="text">{ident}</th>'
        '<th rowspan="3" class="text">SCHOOL NAME</th>'
        '<th rowspan="3" class="text">OWNERSHIP</th>'
        '<th colspan="7">NUMBER OF CANDIDATES</th>'
        f'<th colspan="{div_span}">DIVISION PERFORMANCE</th>'
        '<th rowspan="3">GPA</th>'
        '<th rowspan="3">COMPETENCY LEVEL</th>'
        '<th rowspan="3" class="nw vcell"><span class="rot">C/RANK</span></th>'
        '<th rowspan="3" class="nw vcell"><span class="rot">R/RANK</span></th>'
    )
    # Row 2: REGISTERED / SAT sub-groups + one heading per division group.
    r2 = ['<th colspan="3">REGISTERED</th>', '<th colspan="4">SAT</th>']
    for label, sub in _DIVISIONS:
        r2.append(f'<th colspan="{len(sub)}">{esc(label)}</th>')
    # Row 3: the leaf F / M / T / % labels.
    r3 = [
        "<th>F</th>",
        "<th>M</th>",
        "<th>T</th>",
        "<th>F</th>",
        "<th>M</th>",
        "<th>T</th>",
        "<th>%</th>",
    ]
    for _, sub in _DIVISIONS:
        for leaf in sub:
            r3.append(f"<th>{leaf.upper() if leaf != '%' else '%'}</th>")
    return "<thead>" f"<tr>{r1}</tr>" f"<tr>{''.join(r2)}</tr>" f"<tr>{''.join(r3)}</tr>" "</thead>"


def _st(row: SchoolRankRow, col: int) -> CellStyle | None:
    """Recovered style for physical column ``col`` of a data row, if carried."""
    return row.styles.get(str(col)) if row.styles else None


def _division_cells(row: SchoolRankRow, pool: TemplatePool, start: int) -> tuple[list[str], int]:
    """Emit the DIVISION PERFORMANCE cells, threading the physical column index.

    ``start`` is the physical column index of the first division cell; the
    counter advances one per emitted ``<td>`` so each cell resolves its own
    recovered fill / font / pitch (the pale division washes visible in the
    reference).
    """
    cells: list[str] = []
    col = start
    for label, sub in _DIVISIONS:
        block = row.division.get(label, {}) if isinstance(row.division, dict) else {}
        pct = row.division.get(f"{label}%", "") if isinstance(row.division, dict) else ""
        for leaf in sub:
            value = pct if leaf == "%" else (block.get(leaf, "") if isinstance(block, dict) else "")
            cells.append(styled_cell(pool, value, _st(row, col), row.pitch))
            col += 1
    return cells, col


def _data_row(row: SchoolRankRow, level: str, pool: TemplatePool) -> str:
    """One school row, every ``<td>`` keyed by its physical column index so the
    recovered fill / font / alignment / row pitch travel onto each cell."""
    ident = row.ward if level == "council" else row.council
    p = row.pitch
    cells = [
        styled_cell(pool, row.sno, _st(row, 0), p),
        styled_cell(pool, ident, _st(row, 1), p, text=True),
        styled_cell(pool, row.school_name, _st(row, 2), p, text=True),
        styled_cell(pool, row.ownership, _st(row, 3), p, text=True),
        styled_cell(pool, row.registered.f, _st(row, 4), p),
        styled_cell(pool, row.registered.m, _st(row, 5), p),
        styled_cell(pool, row.registered.t, _st(row, 6), p),
        styled_cell(pool, row.sat.f, _st(row, 7), p),
        styled_cell(pool, row.sat.m, _st(row, 8), p),
        styled_cell(pool, row.sat.t, _st(row, 9), p),
        styled_cell(pool, row.sat_pct, _st(row, 10), p),
    ]
    div_cells, col = _division_cells(row, pool, 11)
    cells += div_cells
    cells.append(styled_cell(pool, row.gpa, _st(row, col), p))
    cells.append(
        competency_cell(row.competency, row.gpa, pool=pool, style=_st(row, col + 1), pitch=p)
    )
    cells.append(styled_cell(pool, row.council_rank, _st(row, col + 2), p))
    cells.append(styled_cell(pool, row.regional_rank, _st(row, col + 3), p))
    return "<tr>" + "".join(cells) + "</tr>"


def _total_row(label: str, values: list[str], report: SchoolsRankReport, pool: TemplatePool) -> str:
    """A TOTAL summary row, each cell carrying its recovered style + pitch."""
    styles = report.total_styles.get(label, [])
    pitch = report.total_pitch.get(label, 0.0)
    cells: list[str] = []
    for c, v in enumerate(values):
        cs = styles[c] if c < len(styles) else None
        cells.append(styled_cell(pool, v, cs, pitch))
    return f'<tr class="total">{"".join(cells)}</tr>'


def _summary_html(summary: PerformanceTable, pool: TemplatePool) -> str:
    """Render the SUMMARY PERFORMANCE block (header band + captured rows).

    Rows were captured by column index (see ``extract_data._full_capture``);
    they are placed back by index, honouring any stored colspan, so the
    aggregate row and the ``% PASS`` row reproduce exactly - now each cell also
    carries its own recovered fill / font / row pitch.
    """
    n_cols = len(summary.column_headers)
    body: list[str] = []
    for prow in summary.rows:
        cells: list[str] = []
        c = 0
        while c < n_cols:
            text = prow.values.get(str(c), "")
            span = int(prow.values.get(f"{c}.span", "1"))
            cs = prow.styles.get(str(c)) if prow.styles else None
            cells.append(styled_cell(pool, text, cs, prow.pitch, colspan=span))
            c += span
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (
        '<table class="tmpl">'
        f"{_generic_thead(summary.column_headers)}"
        "<tbody>" + "".join(body) + "</tbody>"
        "</table>"
    )


def render_schools_rank(report: SchoolsRankReport) -> str:
    """Render a :class:`~sars.schema.SchoolsRankReport` to a full HTML doc."""
    level = report.meta.level
    pool = TemplatePool(orientation_for(report.meta))
    body = banner_html(report.meta)
    for summary in report.summary:
        body += _summary_html(summary, pool)
    body_rows = [_data_row(row, level, pool) for row in report.rows]
    for label, values in report.totals.items():
        body_rows.append(_total_row(label, values, report, pool))
    body += (
        '<table class="tmpl">'
        f"{_colgroup(level)}"
        f"{_thead(level)}"
        "<tbody>" + "".join(body_rows) + "</tbody>"
        "</table>"
    )
    return document_html(report.meta, body, compact=True, pool=pool)
