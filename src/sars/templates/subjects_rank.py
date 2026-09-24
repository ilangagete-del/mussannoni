"""Subjects-rank template - SELF-CONTAINED and FAITHFUL.

Serves the ``subjects_rank`` report type (council and region level): subjects
ranked by their grade breakdown and GPA. This template OWNS its structure and
its complete inline styling: the ``GRADE PERFORMANCE`` grouped header, the
per-column fill washes (the ``A-C`` / ``A-D`` and GPA tints) and the rotated /
plain rank column, all authored HERE at the reference's true point sizes. It
shares no cross-report CSS constant.

DATA IS DATA: the counts are data; the washes are this report type's fixed
chrome; the competency band colour is derived deterministically
(:mod:`sars.competency`).

Expected data shape: a :class:`~sars.schema.SubjectsRankReport` (see the schema
docstrings).
"""

from __future__ import annotations

from ..schema import SubjectsRankReport
from .base import banner_html, competency_background, orientation_for
from .styling import Sheet, document, esc, fit_scale

#: Grade / summary columns in printed order, with the wash class each carries.
_GRADE_COLS: tuple[tuple[str, str], ...] = (
    ("A", ""),
    ("B", ""),
    ("C", ""),
    ("D", ""),
    ("F", "bg-f"),
    ("TOTAL", "bg-total"),
    ("A-C", "bg-ac"),
    ("%A-C", "bg-ac"),
    ("A-D", "bg-ad"),
    ("%A-D", "bg-ad"),
)

_PT_DATA = 6.0
_PT_ROW = 8.4
_PT_BANNER = 7.5


def _style(orientation: str) -> Sheet:
    s = fit_scale(orientation)
    px = lambda pt: f"{pt * s:.2f}pt"  # noqa: E731
    sheet = Sheet()
    sheet.extend(f"""
body{{margin:0;color:#000;font-family:Arial, Helvetica, sans-serif}}
.report{{padding:{px(4)} {px(6)}}}
.banner{{text-align:center;font-weight:700;font-size:{px(_PT_BANNER)};line-height:1.4}}
.banner .title{{margin-top:{px(6)};font-size:{px(_PT_BANNER)}}}
table.sj{{border-collapse:collapse;table-layout:fixed;width:100%;
        border-spacing:0;margin-top:{px(6)}}}
table.sj th,table.sj td{{border:0.4pt solid #000;padding:0 0.8pt;
        text-align:center;vertical-align:middle;overflow:visible;
        font-size:{px(_PT_DATA)};line-height:{px(_PT_ROW)};
        white-space:normal;overflow-wrap:normal;word-break:keep-all}}
table.sj th{{font-weight:700}}
table.sj td.text,table.sj th.text{{text-align:left}}
table.sj tr.total th,table.sj tr.total td{{font-weight:700}}
.bg-f{{background-color:#fcd5b4}}
.bg-total{{background-color:#ebf1de}}
.bg-ac{{background-color:#65ffab}}
.bg-ad{{background-color:#d2fce6}}
.bg-gpa{{background-color:#ffffcc}}
""")
    return sheet


def caption(labels: list[str], canonical: str, *aliases: str) -> str:
    """The report's own caption for a column, falling back to *canonical*."""
    wanted = {canonical.upper(), *(a.upper() for a in aliases)}
    for label in labels:
        if label and label.upper() in wanted:
            return label
    return canonical


def _thead(labels: list[str]) -> str:
    grade_span = len(_GRADE_COLS)
    r1 = (
        '<th rowspan="2" class="nw">S/NO.</th>'
        '<th rowspan="2" class="text">SUBJECT NAME</th>'
        f'<th colspan="{grade_span}">GRADE PERFORMANCE</th>'
        '<th rowspan="2" class="bg-gpa">GPA</th>'
        f'<th rowspan="2">{esc(caption(labels, "COMPETENCY LEVEL", "COMPENTENCY LEVEL"))}</th>'
        f'<th rowspan="2">{esc(caption(labels, "RANK", "R/RANK", "C/RANK"))}</th>'
    )
    r2 = "".join(
        f'<th class="{cls}">{esc(g)}</th>' if cls else f"<th>{esc(g)}</th>"
        for g, cls in _GRADE_COLS
    )
    return f"<thead><tr>{r1}</tr><tr>{r2}</tr></thead>"


def render_subjects_rank(report: SubjectsRankReport) -> str:
    """Render a :class:`~sars.schema.SubjectsRankReport` to a standalone doc."""
    orientation = orientation_for(report.meta)
    sheet = _style(orientation)
    body_rows: list[str] = []
    for row in report.rows:
        cells = [
            f"<td>{esc(row.sno)}</td>",
            f'<td class="text">{esc(row.subject_name)}</td>',
        ]
        for g, cls in _GRADE_COLS:
            attr = f' class="{cls}"' if cls else ""
            cells.append(f"<td{attr}>{esc(row.grades.get(g, ''))}</td>")
        cells.append(f'<td class="bg-gpa">{esc(row.gpa)}</td>')
        bg = competency_background(row.competency, row.gpa)
        st = f' style="background-color:{bg}"' if bg else ""
        cells.append(f'<td class="text"{st}>{esc(row.competency)}</td>')
        cells.append(f"<td>{esc(row.rank)}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    for _label, values in report.totals.items():
        cells = "".join(f"<td>{esc(v)}</td>" for v in values)
        body_rows.append(f'<tr class="total">{cells}</tr>')
    table = (
        '<table class="sj">'
        f"{_thead(report.column_headers)}"
        "<tbody>" + "".join(body_rows) + "</tbody>"
        "</table>"
    )
    body = '<section class="report">' + banner_html(report.meta) + table + "</section>"
    return document(
        title=report.meta.title or report.meta.name,
        orientation=orientation,
        sheet=sheet,
        body=body,
    )
