"""Subjectwise best-students template (council and region level).

Serves the ``best_students`` family when ``meta.variant == "subjectwise"``. This
is a genuinely different structure from the overall best-students list, which is
why it is its own template rather than a variant flag: where the overall list
ranks candidates on their aggregate and division and prints a DETAILED SUBJECTS
column, a subjectwise list ranks candidates *within one subject* and prints that
subject's ``MARKS`` / ``GRADE`` / ``COMPETENCY LEVEL`` instead.

A report is a list of titled sections, one per subject; each section prints the
same candidate columns. The column headings and the section chrome are static;
the candidate rows are data.

Expected data shape: a :class:`~sars.schema.BestStudentsReport` with

* ``meta``     - :class:`~sars.schema.ReportMeta` (``variant='subjectwise'``);
* ``sections`` - :class:`~sars.schema.BestStudentsSection`, each with a ``title``
  naming the subject and a ``students`` list of
  :class:`~sars.schema.StudentRow` using the subjectwise fields: ``sno``,
  ``council`` (region level) or ``id_no`` (council level), ``school_name``,
  ``category``, ``name``, ``sex``, ``marks``, ``grade``, ``position``,
  ``competency``.

The competency cell's background is derived deterministically from the label via
:mod:`sars.competency`; it is never stored in the data.
"""

from __future__ import annotations

from ..schema import BestStudentsReport, BestStudentsSection, StudentRow
from .base import (
    banner_html,
    cell,
    competency_cell,
    document_html,
    esc,
)

#: Candidate columns, as ``(field, heading, left_aligned)``. A column is printed
#: only when at least one candidate in the section carries a value for it, so
#: the same template serves the council layout (which identifies a candidate by
#: ``ID NO.``) and the region layout (which adds a ``COUNCIL`` column).
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


def _present_columns(students: list[StudentRow]) -> tuple[tuple[str, str, bool], ...]:
    """The subset of :data:`_COLUMNS` any candidate in the section fills."""
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
                # The competency colour is derived deterministically, never data.
                cells.append(competency_cell(value))
            else:
                cells.append(cell(value, text=left))
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


def render_best_students_subjectwise(report: BestStudentsReport) -> str:
    """Render a subjectwise :class:`~sars.schema.BestStudentsReport` to HTML."""
    body = banner_html(report.meta)
    body += "".join(_section_html(sec) for sec in report.sections)
    return document_html(report.meta, body)
