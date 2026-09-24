"""Schools-rank / top-schools template - SELF-CONTAINED and FAITHFUL.

Serves the ``schools_rank`` and ``top_schools`` report types (council and
region level). This template OWNS its complete structure and its complete inline
styling: the grouped-header band (``NUMBER OF CANDIDATES`` / ``DIVISION
PERFORMANCE``), the ``SUMMARY PERFORMANCE`` block, the per-division-group fill
washes, the ``GPA PERFORMANCE`` band, the rotated ``C/RANK`` / ``R/RANK``
columns, and the data-row font size and row height are all reproduced HERE to
match the reference PDF cell-by-cell. It shares no cross-report CSS constant;
its ``<style>`` is inlined into its own ``<head>``.

DATA IS DATA: the row data carries no fonts / colours / fills. The washes are
this report type's fixed chrome painted by the template's own CSS (keyed to the
column group); the only data-derived colour is the competency band, computed
deterministically via :mod:`sars.competency`.

Expected data shape: a :class:`~sars.schema.SchoolsRankReport` (see the schema
docstrings for ``rows`` / ``totals`` / ``summary`` / ``column_headers``).
"""

from __future__ import annotations

from ..schema import PerformanceTable, SchoolRankRow, SchoolsRankReport
from .base import banner_html, competency_background, orientation_for
from .generic import _header_matrix
from .styling import Sheet, document, esc, fit_scale, rot

#: Division-performance sub-columns in printed order and which of F/M/T/% each
#: carries. Percentages sit under ``0``, ``I-III`` and ``I-IV``.
_DIVISIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("I", ("f", "m", "t")),
    ("II", ("f", "m", "t")),
    ("III", ("f", "m", "t")),
    ("IV", ("f", "m", "t")),
    ("0", ("f", "m", "t", "%")),
    ("I-III", ("f", "m", "t", "%")),
    ("I-IV", ("f", "m", "t", "%")),
)

# --------------------------------------------------------------------------- #
# The report type's own fill washes (fixed chrome, keyed to the column group).
# Recovered from the reference PDF; painted by CSS classes, never read from data.
# --------------------------------------------------------------------------- #
#: F/M/T tints inside a division group.
_DIV_FMT_BG = "#d2fce6"
_DIV_T_BG = "#daeef3"
#: The ``0`` (fail) division group + its % column.
_ZERO_FMT_BG = "#fde9d9"
_ZERO_PCT_BG = "#fabf8f"
#: The I-III group and its % column.
_I3_PCT_BG = "#65ffab"
#: SAT % column, GPA column.
_SAT_PCT_BG = "#dce6f1"
_GPA_BG = "#dce6f1"
#: The rank columns.
_CRANK_BG = "#ebf1de"
_RRANK_BG = "#fde9d9"

# True recovered point sizes (pre-scale); multiplied by the fit-to-A4 scale so
# they print at the reference size. Data rows ~3.98pt, group headings a touch
# larger, the banner title 5.68pt (all Arial, as the reference uses).
_PT_DATA = 3.98
_PT_HEAD = 3.98
_PT_TITLE = 5.68
_PT_BANNER = 6.63
#: True row pitch (pt) for a data row; the reference pitch is ~6.6pt.
_PT_ROW = 6.6


def _style(orientation: str) -> Sheet:
    """Build THIS report's own complete inline stylesheet."""
    s = fit_scale(orientation)
    px = lambda pt: f"{pt * s:.2f}pt"  # noqa: E731 - local shorthand
    sheet = Sheet()
    sheet.extend(f"""
body{{margin:0;color:#000;font-family:Arial, Helvetica, sans-serif}}
.report{{padding:{px(4)} {px(6)}}}
.banner{{text-align:center;font-weight:700;font-size:{px(_PT_BANNER)};
        line-height:1.4}}
.banner .title{{margin-top:{px(6)};font-size:{px(_PT_BANNER)}}}
table.sr{{border-collapse:collapse;table-layout:fixed;width:100%;
        border-spacing:0;margin-top:{px(6)}}}
table.sr th,table.sr td{{border:0.4pt solid #000;padding:0 0.6pt;
        text-align:center;vertical-align:middle;overflow:visible;
        font-size:{px(_PT_DATA)};line-height:{px(_PT_ROW)};
        white-space:normal;overflow-wrap:normal;word-break:keep-all}}
table.sr th{{font-weight:700;font-size:{px(_PT_HEAD)}}}
table.sr td{{font-weight:700}}
table.sr td.text,table.sr th.text{{text-align:left}}
table.sr th.nw,table.sr td.nw{{white-space:nowrap}}
table.sr tr.total th,table.sr tr.total td{{font-weight:700}}
/* Vertical rank captions: WeasyPrint has no writing-mode, so rotate(). */
.rot{{display:inline-block;transform:rotate(-90deg);transform-origin:50% 50%;
      white-space:nowrap;line-height:1}}
th.vcell,td.vcell{{overflow:visible}}
/* This report type's own fill washes (fixed chrome, keyed to column group). */
.bg-fmt{{background-color:{_DIV_FMT_BG}}}
.bg-t{{background-color:{_DIV_T_BG}}}
.bg-zero{{background-color:{_ZERO_FMT_BG}}}
.bg-zeropct{{background-color:{_ZERO_PCT_BG}}}
.bg-i3pct{{background-color:{_I3_PCT_BG}}}
.bg-satpct{{background-color:{_SAT_PCT_BG}}}
.bg-gpa{{background-color:{_GPA_BG}}}
.bg-crank{{background-color:{_CRANK_BG}}}
.bg-rrank{{background-color:{_RRANK_BG}}}
""")
    return sheet


def _colgroup(level: str) -> str:
    """Proportional column widths so wide text columns get room and the many
    numeric columns stay narrow (a long SCHOOL NAME must not overhang into and
    merge with its neighbour)."""
    widths: list[float] = [2.0, 5.5, 8.0, 4.0]  # S/NO, ident, school, ownership
    widths += [2.1, 2.1, 2.1, 2.1, 2.1, 2.1, 2.1]  # registered F/M/T + sat F/M/T/%
    div_span = sum(len(sub) for _, sub in _DIVISIONS)
    widths += [1.95] * div_span
    # gpa, competency, c/rank, r/rank (rank cols narrow: their headers rotate).
    widths += [3.6, 9.0, 2.2, 2.2]
    total = sum(widths)
    cols = "".join(f'<col style="width:{w / total * 100:.4f}%">' for w in widths)
    return f"<colgroup>{cols}</colgroup>"


def _division_cells(row: SchoolRankRow) -> list[str]:
    """Emit the DIVISION PERFORMANCE cells from pure data, wash by column."""
    cells: list[str] = []
    for label, sub in _DIVISIONS:
        block = row.division.get(label, {}) if isinstance(row.division, dict) else {}
        pct = row.division.get(f"{label}%", "") if isinstance(row.division, dict) else ""
        for leaf in sub:
            value = pct if leaf == "%" else (block.get(leaf, "") if isinstance(block, dict) else "")
            cls = _leaf_wash(label, leaf)
            attr = f' class="{cls}"' if cls else ""
            cells.append(f"<td{attr}>{esc(value)}</td>")
    return cells


def _leaf_wash(label: str, leaf: str) -> str:
    """The wash class for a division leaf, matching the reference PDF."""
    if label in ("I", "II", "III", "IV"):
        return "bg-t" if leaf == "t" else "bg-fmt"
    if label == "0":
        return "bg-zeropct" if leaf == "%" else "bg-zero"
    if label == "I-III":
        return "bg-i3pct" if leaf == "%" else "bg-fmt"
    if label == "I-IV":
        return "bg-t"
    return ""


def _cell(value: str, *, text: bool = False, cls: str = "", colspan: int = 1) -> str:
    classes = " ".join(c for c in (("text" if text else ""), cls) if c)
    attrs = f' class="{classes}"' if classes else ""
    if colspan > 1:
        attrs += f' colspan="{colspan}"'
    return f"<td{attrs}>{esc(value)}</td>"


def _competency_cell(label: str, gpa: str) -> str:
    bg = competency_background(label, gpa)
    style = f' style="background-color:{bg}"' if bg else ""
    return f'<td class="text"{style}>{esc(label)}</td>'


def _data_row(row: SchoolRankRow, level: str) -> str:
    """One school row rendered from pure data, with the report's own washes."""
    ident = row.ward if level == "council" else row.council
    cells = [
        _cell(row.sno),
        _cell(ident, text=True),
        _cell(row.school_name, text=True),
        _cell(row.ownership, text=True),
        _cell(row.registered.f),
        _cell(row.registered.m),
        _cell(row.registered.t),
        _cell(row.sat.f),
        _cell(row.sat.m),
        _cell(row.sat.t),
        _cell(row.sat_pct, cls="bg-satpct"),
    ]
    cells += _division_cells(row)
    cells.append(_cell(row.gpa, cls="bg-gpa"))
    cells.append(_competency_cell(row.competency, row.gpa))
    cells.append(_cell(row.council_rank, cls="bg-crank"))
    cells.append(_cell(row.regional_rank, cls="bg-rrank"))
    return "<tr>" + "".join(cells) + "</tr>"


def _total_row(values: list[str]) -> str:
    """A TOTAL summary row rendered from pure data."""
    cells = "".join(f"<td>{esc(v)}</td>" for v in values)
    return f'<tr class="total">{cells}</tr>'


def _thead(level: str) -> str:
    """The three-row grouped header band (chrome), with group washes."""
    ident = "WARD" if level == "council" else "COUNCIL"
    div_span = sum(len(sub) for _, sub in _DIVISIONS)
    r1 = (
        '<th rowspan="3" class="nw">S/NO.</th>'
        f'<th rowspan="3" class="text">{ident}</th>'
        '<th rowspan="3" class="text">SCHOOL NAME</th>'
        '<th rowspan="3" class="text">OWNERSHIP</th>'
        '<th colspan="7">NUMBER OF CANDIDATES</th>'
        f'<th colspan="{div_span}">DIVISION PERFORMANCE</th>'
        '<th rowspan="3" class="bg-gpa">GPA</th>'
        '<th rowspan="3">COMPETENCY LEVEL</th>'
        '<th rowspan="3" class="nw vcell bg-crank">C/RANK</th>'
        '<th rowspan="3" class="nw vcell bg-rrank">R/RANK</th>'
    )
    r2 = ['<th colspan="3">REGISTERED</th>', '<th colspan="4">SAT</th>']
    for label, sub in _DIVISIONS:
        r2.append(f'<th colspan="{len(sub)}">{esc(label)}</th>')
    r3 = [
        "<th>F</th>",
        "<th>M</th>",
        "<th>T</th>",
        "<th>F</th>",
        "<th>M</th>",
        "<th>T</th>",
        '<th class="bg-satpct">%</th>',
    ]
    for label, sub in _DIVISIONS:
        for leaf in sub:
            cls = _leaf_wash(label, leaf)
            attr = f' class="{cls}"' if cls else ""
            r3.append(f"<th{attr}>{leaf.upper() if leaf != '%' else '%'}</th>")
    # Rotate the two rank captions.
    r1 = r1.replace(">C/RANK<", f">{rot('C/RANK')}<").replace(">R/RANK<", f">{rot('R/RANK')}<")
    return "<thead>" f"<tr>{r1}</tr>" f"<tr>{''.join(r2)}</tr>" f"<tr>{''.join(r3)}</tr>" "</thead>"


def _summary_html(summary: PerformanceTable) -> str:
    """Render the SUMMARY / GPA PERFORMANCE block above the ranked table."""
    n_cols = len(summary.column_headers)
    body: list[str] = []
    for prow in summary.rows:
        cells: list[str] = []
        c = 0
        while c < n_cols:
            text = prow.values.get(str(c), "")
            span = int(prow.values.get(f"{c}.span", "1"))
            cells.append(_cell(text, colspan=span))
            c += span
        body.append("<tr>" + "".join(cells) + "</tr>")
    # Grouped header band, so NUMBER OF CANDIDATES / DIVISION PERFORMANCE / GPA
    # PERFORMANCE span their sub-columns like the reference instead of repeating
    # the full label path in every leaf cell.
    matrix = _header_matrix(summary.column_headers)
    head_rows = []
    for hrow in matrix:
        cells = "".join(
            f'<th colspan="{span}">{esc(text)}</th>' if span > 1 else f"<th>{esc(text)}</th>"
            for text, span in hrow
        )
        head_rows.append(f"<tr>{cells}</tr>")
    return (
        '<table class="sr">'
        f"<thead>{''.join(head_rows)}</thead>"
        "<tbody>" + "".join(body) + "</tbody>"
        "</table>"
    )


def render_schools_rank(report: SchoolsRankReport) -> str:
    """Render a :class:`~sars.schema.SchoolsRankReport` to a standalone HTML doc."""
    level = report.meta.level
    orientation = orientation_for(report.meta)
    sheet = _style(orientation)

    body = '<section class="report">'
    body += banner_html(report.meta)
    for summary in report.summary:
        body += _summary_html(summary)
    body_rows = [_data_row(row, level) for row in report.rows]
    for _label, values in report.totals.items():
        body_rows.append(_total_row(values))
    body += (
        '<table class="sr">'
        f"{_colgroup(level)}"
        f"{_thead(level)}"
        "<tbody>" + "".join(body_rows) + "</tbody>"
        "</table>"
    )
    body += "</section>"
    return document(
        title=report.meta.title or report.meta.name,
        orientation=orientation,
        sheet=sheet,
        body=body,
    )
