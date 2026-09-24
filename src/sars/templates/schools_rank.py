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

from ..schema import PerformanceTable, SchoolRankRow, SchoolsRankReport
from .base import banner_html, competency_cell, document_html, esc
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


def _colgroup(level: str, ranks: tuple[bool, bool] = (True, True)) -> str:
    """Proportional column widths so wide text columns get room and the many
    numeric columns stay narrow - preventing a long SCHOOL NAME from overhanging
    into its neighbour (which the PDF text extractor would merge into one token)
    while still fitting every column on one page."""
    has_c, has_r = ranks
    widths: list[float] = [2.0, 5.5, 8.0, 4.0]  # S/NO, ident, school, ownership
    widths += [2.1, 2.1, 2.1, 2.1, 2.1, 2.1, 2.1]  # registered F/M/T + sat F/M/T/%
    div_span = sum(len(sub) for _, sub in _DIVISIONS)
    widths += [1.95] * div_span
    widths += [3.6, 8.5]  # gpa, competency
    if has_c:
        widths.append(2.0)  # c/rank
    if has_r:
        widths.append(2.0)  # r/rank
    total = sum(widths)
    cols = "".join(f'<col style="width:{w / total * 100:.4f}%">' for w in widths)
    return f"<colgroup>{cols}</colgroup>"


def _rank_columns(report: SchoolsRankReport) -> tuple[bool, bool]:
    """Which trailing rank columns this report prints: ``(council, regional)``.

    The reports differ: a council top-ten prints only ``C/RANK``, a region
    top-ten only ``R/RANK``, and a full ranking prints both. The captured column
    headers state which are present; a report that carries a rank *value* but no
    caption (older data) still shows the column so no value is dropped.
    """
    caps = {c.upper() for c in report.column_headers}
    has_c = "C/RANK" in caps or any(r.council_rank for r in report.rows)
    has_r = "R/RANK" in caps or any(r.regional_rank for r in report.rows)
    if not (has_c or has_r):  # nothing said either way -> keep both
        return True, True
    return has_c, has_r


def _thead(level: str, ranks: tuple[bool, bool] = (True, True)) -> str:
    """The three-row grouped header band (chrome)."""
    ident = "WARD" if level == "council" else "COUNCIL"
    has_c, has_r = ranks
    # Row 1: identity columns (rowspan 3) + the two big group headings + GPA
    #        block + competency + rank columns.
    div_span = sum(len(sub) for _, sub in _DIVISIONS)
    rank_th = ""
    if has_c:
        rank_th += '<th rowspan="3" class="nw">C/RANK</th>'
    if has_r:
        rank_th += '<th rowspan="3" class="nw">R/RANK</th>'
    r1 = (
        '<th rowspan="3" class="nw">S/NO.</th>'
        f'<th rowspan="3" class="text">{ident}</th>'
        '<th rowspan="3" class="text">SCHOOL NAME</th>'
        '<th rowspan="3" class="text">OWNERSHIP</th>'
        '<th colspan="7">NUMBER OF CANDIDATES</th>'
        f'<th colspan="{div_span}">DIVISION PERFORMANCE</th>'
        '<th rowspan="3">GPA</th>'
        '<th rowspan="3">COMPETENCY LEVEL</th>'
        f"{rank_th}"
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
    cells: list[str] = []
    for label, sub in _DIVISIONS:
        block = row.division.get(label, {}) if isinstance(row.division, dict) else {}
        pct = row.division.get(f"{label}%", "") if isinstance(row.division, dict) else ""
        for leaf in sub:
            if leaf == "%":
                cells.append(f"<td>{esc(pct)}</td>")
            else:
                value = block.get(leaf, "") if isinstance(block, dict) else ""
                cells.append(f"<td>{esc(value)}</td>")
    return cells


def _data_row(row: SchoolRankRow, level: str, ranks: tuple[bool, bool] = (True, True)) -> str:
    has_c, has_r = ranks
    ident = row.ward if level == "council" else row.council
    cells = [
        f"<td>{esc(row.sno)}</td>",
        f'<td class="text">{esc(ident)}</td>',
        f'<td class="text">{esc(row.school_name)}</td>',
        f'<td class="text">{esc(row.ownership)}</td>',
        f"<td>{esc(row.registered.f)}</td>",
        f"<td>{esc(row.registered.m)}</td>",
        f"<td>{esc(row.registered.t)}</td>",
        f"<td>{esc(row.sat.f)}</td>",
        f"<td>{esc(row.sat.m)}</td>",
        f"<td>{esc(row.sat.t)}</td>",
        f"<td>{esc(row.sat_pct)}</td>",
    ]
    cells += _division_cells(row)
    cells += [
        f"<td>{esc(row.gpa)}</td>",
        competency_cell(row.competency, row.gpa),
    ]
    if has_c:
        cells.append(f"<td>{esc(row.council_rank)}</td>")
    if has_r:
        cells.append(f"<td>{esc(row.regional_rank)}</td>")
    return "<tr>" + "".join(cells) + "</tr>"


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
            span_attr = f' colspan="{span}"' if span > 1 else ""
            cells.append(f"<td{span_attr}>{esc(text)}</td>")
            c += span
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (
        '<table class="tmpl">'
        f"{_generic_thead(summary.column_headers)}"
        "<tbody>" + "".join(body) + "</tbody>"
        "</table>"
    )


def _one_table(level: str, rows_html: list[str], ranks: tuple[bool, bool]) -> str:
    return (
        '<table class="tmpl">'
        f"{_colgroup(level, ranks)}"
        f"{_thead(level, ranks)}"
        "<tbody>" + "".join(rows_html) + "</tbody>"
        "</table>"
    )


def render_schools_rank(report: SchoolsRankReport) -> str:
    """Render a :class:`~sars.schema.SchoolsRankReport` to a full HTML doc.

    A plain ranking is one table. A top-ten report is a sequence of titled
    blocks (``section_titles`` / ``section_row_counts``): the heading of each is
    printed above its own table, so "TOP 10 BEST PRIVATE SCHOOLS" and "TEN LOOSER
    SCHOOLS OVERALL" appear exactly as in the reference rather than being fused
    into one continuous list.
    """
    level = report.meta.level
    ranks = _rank_columns(report)
    body = banner_html(report.meta)
    for summary in report.summary:
        body += _summary_html(summary)

    titles = report.section_titles
    counts = report.section_row_counts
    if titles and counts and sum(counts) == len(report.rows):
        start = 0
        for title, n in zip(titles, counts, strict=False):
            block = [_data_row(row, level, ranks) for row in report.rows[start : start + n]]
            if title:
                body += f'<div class="banner"><div class="title">{esc(title)}</div></div>'
            body += _one_table(level, block, ranks)
            start += n
        # Totals belong to the whole report; print them once after the blocks.
        if report.totals:
            total_rows = [
                f'<tr class="total">{"".join(f"<td>{esc(v)}</td>" for v in values)}</tr>'
                for values in report.totals.values()
            ]
            body += _one_table(level, total_rows, ranks)
        return document_html(report.meta, body, compact=True)

    body_rows = [_data_row(row, level, ranks) for row in report.rows]
    for _label, values in report.totals.items():
        cells = "".join(f"<td>{esc(v)}</td>" for v in values)
        body_rows.append(f'<tr class="total">{cells}</tr>')
    body += _one_table(level, body_rows, ranks)
    return document_html(report.meta, body, compact=True)
