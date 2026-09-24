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

DATA IS DATA: the row data carries no recovered fonts / colours / fills, so the
cells render plain (FEAT-003 owns the faithful styling); only the competency
band colour is derived deterministically from the data.
"""

from __future__ import annotations

from ..schema import PerformanceTable, SchoolRankRow, SchoolsRankReport
from .base import (
    banner_html,
    competency_cell,
    document_html,
    esc,
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
    # C/RANK and R/RANK are single nowrap tokens; give them enough width that
    # the caption does not overhang into - and merge with - its neighbour.
    widths += [3.6, 8.5, 4.5, 4.5]  # gpa, competency, c/rank, r/rank
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
        '<th rowspan="3" class="nw">C/RANK</th>'
        '<th rowspan="3" class="nw">R/RANK</th>'
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


def _division_cells(row: SchoolRankRow) -> list[str]:
    """Emit the DIVISION PERFORMANCE cells from pure data."""
    cells: list[str] = []
    for label, sub in _DIVISIONS:
        block = row.division.get(label, {}) if isinstance(row.division, dict) else {}
        pct = row.division.get(f"{label}%", "") if isinstance(row.division, dict) else ""
        for leaf in sub:
            value = pct if leaf == "%" else (block.get(leaf, "") if isinstance(block, dict) else "")
            cells.append(styled_cell(value))
    return cells


def _data_row(row: SchoolRankRow, level: str) -> str:
    """One school row rendered from pure data."""
    ident = row.ward if level == "council" else row.council
    cells = [
        styled_cell(row.sno),
        styled_cell(ident, text=True),
        styled_cell(row.school_name, text=True),
        styled_cell(row.ownership, text=True),
        styled_cell(row.registered.f),
        styled_cell(row.registered.m),
        styled_cell(row.registered.t),
        styled_cell(row.sat.f),
        styled_cell(row.sat.m),
        styled_cell(row.sat.t),
        styled_cell(row.sat_pct),
    ]
    cells += _division_cells(row)
    cells.append(styled_cell(row.gpa))
    cells.append(competency_cell(row.competency, row.gpa))
    cells.append(styled_cell(row.council_rank))
    cells.append(styled_cell(row.regional_rank))
    return "<tr>" + "".join(cells) + "</tr>"


def _total_row(label: str, values: list[str]) -> str:
    """A TOTAL summary row rendered from pure data."""
    cells = "".join(styled_cell(v) for v in values)
    return f'<tr class="total">{cells}</tr>'


def _summary_html(summary: PerformanceTable) -> str:
    """Render the SUMMARY PERFORMANCE block (header band + captured rows).

    Rows were captured by column index (see ``extract_data._full_capture``);
    they are placed back by index, honouring any stored colspan, so the
    aggregate row and the ``% PASS`` row reproduce exactly.
    """
    n_cols = len(summary.column_headers)
    body: list[str] = []
    for prow in summary.rows:
        cells: list[str] = []
        c = 0
        while c < n_cols:
            text = prow.values.get(str(c), "")
            span = int(prow.values.get(f"{c}.span", "1"))
            cells.append(styled_cell(text, colspan=span))
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
    body = banner_html(report.meta)
    for summary in report.summary:
        body += _summary_html(summary)
    body_rows = [_data_row(row, level) for row in report.rows]
    for label, values in report.totals.items():
        body_rows.append(_total_row(label, values))
    body += (
        '<table class="tmpl">'
        f"{_colgroup(level)}"
        f"{_thead(level)}"
        "<tbody>" + "".join(body_rows) + "</tbody>"
        "</table>"
    )
    return document_html(report.meta, body, compact=True)
