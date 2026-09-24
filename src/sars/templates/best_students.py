"""Top-ten best-students template (overall and subjectwise variants).

Serves the ``best_students`` report type at council and region level. A report
is a list of titled sections (overall / female / male, or one per subject); each
section prints the same candidate columns. The fixed column headings are chrome;
the candidate rows are data.

Expected data shape: a :class:`~sars.schema.BestStudentsReport` with

* ``meta``     - :class:`~sars.schema.ReportMeta`;
* ``sections`` - :class:`~sars.schema.BestStudentsSection`, each with a
  ``title`` (the heading naming the block) and ``students`` list of
  :class:`~sars.schema.StudentRow` (cno, school_name, name, sex, aggregate,
  division, position, detailed_subjects / parsed subjects).
"""

from __future__ import annotations

from ..schema import BestStudentsReport, BestStudentsSection, StudentRow
from .base import TemplatePool, banner_html, cell, document_html, esc, orientation_for
from .best_students_subjectwise import render_best_students_subjectwise

#: Candidate columns as ``(field, heading, left_aligned)``. A column is printed
#: only when some candidate in the section fills it, so one template serves both
#: the council layout and the region layout (which adds ``S/NO.`` + ``COUNCIL``).
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


def _present_columns(students: list[StudentRow]) -> tuple[tuple[str, str, bool], ...]:
    """The subset of :data:`_COLUMNS` any candidate in the section fills."""
    return tuple(
        col
        for col in _COLUMNS
        if any(str(getattr(st, col[0], "") or "").strip() for st in students)
    )


def _section_html(section: BestStudentsSection, pool: TemplatePool) -> str:
    if not section.students:
        return ""
    columns = _present_columns(section.students)
    head = "".join(
        f'<th class="text">{esc(heading)}</th>' if left else f"<th>{esc(heading)}</th>"
        for _field, heading, left in columns
    )
    rows: list[str] = []
    for st in section.students:
        # StudentRow styles are keyed by field name (see extract_data), so each
        # cell recovers the font / colour / fill and row pitch of its own column.
        cells = [
            cell(
                str(getattr(st, field_name, "") or ""),
                text=left,
                pool=pool,
                style=st.styles.get(field_name) if st.styles else None,
                pitch=st.pitch,
            )
            for field_name, _heading, left in columns
        ]
        rows.append("<tr>" + "".join(cells) + "</tr>")
    title = (
        f'<div class="banner"><div class="title">{esc(section.title)}</div></div>'
        if section.title
        else ""
    )
    return (
        title
        + '<table class="tmpl">'
        + f"<thead><tr>{head}</tr></thead>"
        + "<tbody>"
        + "".join(rows)
        + "</tbody>"
        + "</table>"
    )


def render_best_students(report: BestStudentsReport) -> str:
    """Render a :class:`~sars.schema.BestStudentsReport` to a full HTML doc.

    Dispatches to the subjectwise template when the report is a subjectwise list,
    because that layout prints a subject's mark/grade/competency per candidate
    instead of an aggregate, division and detailed-subjects breakdown.
    """
    if (report.meta.variant or "").lower() == "subjectwise":
        return render_best_students_subjectwise(report)
    pool = TemplatePool(orientation_for(report.meta))
    body = banner_html(report.meta)
    body += "".join(_section_html(sec, pool) for sec in report.sections)
    return document_html(report.meta, body, pool=pool)
