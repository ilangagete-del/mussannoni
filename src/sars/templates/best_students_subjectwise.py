"""Subjectwise best-students template - SELF-CONTAINED and FAITHFUL.

Serves the ``best_students`` family when ``meta.variant == "subjectwise"``: a
list of titled sections (one per subject), each ranking candidates within one
subject with that subject's ``MARKS`` / ``GRADE`` / ``COMPETENCY LEVEL``. This
template OWNS its structure and its complete inline styling, authored at the
reference's true point sizes; it shares no cross-report CSS constant.

DATA IS DATA: the candidate rows are data; the competency band colour is derived
deterministically (:mod:`sars.competency`), never stored.
"""

from __future__ import annotations

from ..schema import BestStudentsReport, BestStudentsSection, StudentRow
from .base import banner_html, competency_background, orientation_for
from .styling import Sheet, document, esc, fit_scale

#: Candidate columns, as ``(field, heading, left_aligned)``.
_COLUMNS: tuple[tuple[str, str, bool], ...] = (
    ("sno", "S/NO.", False),
    ("council", "COUNCIL", True),
    ("id_no", "ID NO.", False),
    ("cno", "C/NO", False),
    ("school_name", "SCHOOL", True),
    ("category", "CATEGORY", True),
    ("name", "CANDIDATE FULL NAME", True),
    ("sex", "SEX", False),
    ("marks", "MARKS", False),
    ("grade", "GRADE", False),
    ("position", "POSITION", False),
    ("competency", "COMPETENCY LEVEL", True),
)

_PT_DATA = 8.0
_PT_ROW = 11.5
_PT_BANNER = 8.5


def _style(orientation: str) -> Sheet:
    s = fit_scale(orientation)
    px = lambda pt: f"{pt * s:.2f}pt"  # noqa: E731
    sheet = Sheet()
    sheet.extend(f"""
body{{margin:0;color:#000;font-family:Arial, Helvetica, sans-serif}}
.report{{padding:{px(4)} {px(6)}}}
.banner{{text-align:center;font-weight:700;font-size:{px(_PT_BANNER)};line-height:1.4}}
.banner .title{{margin-top:{px(6)};font-size:{px(_PT_BANNER)}}}
table.bw{{border-collapse:collapse;table-layout:fixed;width:100%;
        border-spacing:0;margin-top:{px(6)}}}
table.bw th,table.bw td{{border:0.4pt solid #000;padding:0 1pt;
        text-align:center;vertical-align:middle;overflow:visible;
        font-size:{px(_PT_DATA)};line-height:{px(_PT_ROW)};
        white-space:normal;overflow-wrap:normal;word-break:keep-all}}
table.bw th{{font-weight:700}}
table.bw td.text,table.bw th.text{{text-align:left}}
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
        cells: list[str] = []
        for field_name, _heading, left in columns:
            value = str(getattr(st, field_name, "") or "")
            if field_name == "competency":
                bg = competency_background(value)
                stx = f' style="background-color:{bg}"' if bg else ""
                cells.append(f'<td class="text"{stx}>{esc(value)}</td>')
            else:
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
        + '<table class="bw">'
        + f"<thead><tr>{head}</tr></thead>"
        + "<tbody>"
        + "".join(rows)
        + "</tbody>"
        + "</table>"
    )


def render_best_students_subjectwise(report: BestStudentsReport) -> str:
    """Render a subjectwise :class:`~sars.schema.BestStudentsReport` to a doc."""
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
