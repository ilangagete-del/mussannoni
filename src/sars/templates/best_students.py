"""Top-ten best-students template - SELF-CONTAINED and FAITHFUL.

Serves the ``best_students`` report type at council and region level. A report
is a list of titled sections (overall / female / male); each section prints the
same candidate columns. This template OWNS its structure and its complete inline
styling, authored at the reference's true point sizes; it shares no cross-report
CSS constant.

DATA IS DATA: the candidate rows are data; the competency band colour (on the
subjectwise variant) is derived deterministically (:mod:`sars.competency`).
"""

from __future__ import annotations

from ..schema import BestStudentsReport, BestStudentsSection, StudentRow
from .base import banner_html, orientation_for
from .best_students_subjectwise import render_best_students_subjectwise
from .styling import Sheet, document, esc, fit_scale

#: Candidate columns as ``(field, heading, left_aligned)``. A column is printed
#: only when some candidate in the section fills it.
_COLUMNS: tuple[tuple[str, str, bool], ...] = (
    ("sno", "S/NO.", False),
    ("council", "COUNCIL", True),
    ("cno", "C/NO", False),
    ("school_name", "SCHOOL NAME", True),
    ("name", "CANDIDATE FULL NAME", True),
    ("sex", "SEX", False),
    ("aggregate", "AGGT", False),
    ("division", "DIVISION", False),
    ("position", "POS", False),
    ("detailed_subjects", "DETAILED SUBJECTS", True),
)

_PT_DATA = 6.4
_PT_ROW = 9.0
_PT_BANNER = 8.0


def _style(orientation: str) -> Sheet:
    s = fit_scale(orientation)
    px = lambda pt: f"{pt * s:.2f}pt"  # noqa: E731
    sheet = Sheet()
    sheet.extend(f"""
body{{margin:0;color:#000;font-family:Arial, Helvetica, sans-serif}}
.report{{padding:{px(4)} {px(6)}}}
.banner{{text-align:center;font-weight:700;font-size:{px(_PT_BANNER)};line-height:1.4}}
.banner .title{{margin-top:{px(6)};font-size:{px(_PT_BANNER)}}}
table.bs{{border-collapse:collapse;table-layout:fixed;width:100%;
        border-spacing:0;margin-top:{px(6)}}}
table.bs th,table.bs td{{border:0.4pt solid #000;padding:0 1pt;
        text-align:center;vertical-align:middle;overflow:visible;
        font-size:{px(_PT_DATA)};line-height:{px(_PT_ROW)};
        white-space:normal;overflow-wrap:normal;word-break:keep-all}}
table.bs th{{font-weight:700}}
table.bs td.text,table.bs th.text{{text-align:left}}
""")
    return sheet


def _present_columns(students: list[StudentRow]) -> tuple[tuple[str, str, bool], ...]:
    return tuple(
        col
        for col in _COLUMNS
        if any(str(getattr(st, col[0], "") or "").strip() for st in students)
    )


def _section_html(section: BestStudentsSection) -> str:
    if not section.students:
        return ""
    columns = _present_columns(section.students)
    head = "".join(
        f'<th class="text">{esc(heading)}</th>' if left else f"<th>{esc(heading)}</th>"
        for _field, heading, left in columns
    )
    rows: list[str] = []
    for st in section.students:
        cells = []
        for field_name, _heading, left in columns:
            value = str(getattr(st, field_name, "") or "")
            cls = ' class="text"' if left else ""
            cells.append(f"<td{cls}>{esc(value)}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    title = (
        f'<div class="banner"><div class="title">{esc(section.title)}</div></div>'
        if section.title
        else ""
    )
    return (
        title
        + '<table class="bs">'
        + f"<thead><tr>{head}</tr></thead>"
        + "<tbody>"
        + "".join(rows)
        + "</tbody>"
        + "</table>"
    )


def render_best_students(report: BestStudentsReport) -> str:
    """Render a :class:`~sars.schema.BestStudentsReport` to a standalone doc.

    Dispatches to the subjectwise template for a subjectwise list.
    """
    if (report.meta.variant or "").lower() == "subjectwise":
        return render_best_students_subjectwise(report)
    orientation = orientation_for(report.meta)
    sheet = _style(orientation)
    body = '<section class="report">' + banner_html(report.meta)
    body += "".join(_section_html(sec) for sec in report.sections)
    body += "</section>"
    return document(
        title=report.meta.title or report.meta.name,
        orientation=orientation,
        sheet=sheet,
        body=body,
    )
