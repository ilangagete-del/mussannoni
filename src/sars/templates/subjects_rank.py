"""Subjects-rank template.

Serves the ``subjects_rank`` report type (council and region level): subjects
ranked by their grade breakdown and GPA. The grade-column headings and the
``TOTAL`` / ``A-C`` / ``A-D`` summary columns are chrome; the per-subject counts
are data.

Expected data shape: a :class:`~sars.schema.SubjectsRankReport` with

* ``meta``   - :class:`~sars.schema.ReportMeta`;
* ``rows``   - :class:`~sars.schema.SubjectRankRow` (sno, subject_name, a
  ``grades`` map keyed by grade label, gpa, competency, rank);
* ``totals`` - ``{label: [cell, ...]}`` for any summary row.
"""

from __future__ import annotations

from ..schema import SubjectsRankReport
from .base import (
    banner_html,
    competency_cell,
    document_html,
    header_cell,
    styled_cell,
)

#: Grade / summary columns in printed order.
_GRADE_COLS = ("A", "B", "C", "D", "F", "TOTAL", "A-C", "%A-C", "A-D", "%A-D")


def caption(labels: list[str], canonical: str, *aliases: str) -> str:
    """The report's own caption for a column, falling back to *canonical*.

    Headings are chrome and live in the template, but individual reports spell a
    heading differently - ``RANK`` vs ``R/RANK``, and the ``COMPENTENCY LEVEL``
    spelling used by the source PDFs. When the data carries the report's captured
    captions the matching one is used, so a given report reproduces exactly;
    otherwise the canonical spelling is printed.
    """
    wanted = {canonical.upper(), *(a.upper() for a in aliases)}
    for label in labels:
        if label and label.upper() in wanted:
            return label
    return canonical


def _thead(labels: list[str]) -> str:
    head = [header_cell("S/NO."), header_cell("SUBJECT NAME", text=True)]
    head += [header_cell(g) for g in _GRADE_COLS]
    head += [
        header_cell("GPA"),
        header_cell(caption(labels, "COMPETENCY LEVEL", "COMPENTENCY LEVEL")),
        header_cell(caption(labels, "RANK", "R/RANK", "C/RANK")),
    ]
    return f"<thead><tr>{''.join(head)}</tr></thead>"


def render_subjects_rank(report: SubjectsRankReport) -> str:
    """Render a :class:`~sars.schema.SubjectsRankReport` to a full HTML doc.

    Rendered from pure data (no recovered per-cell styling); only the competency
    band colour is derived deterministically from the data.
    """
    body_rows: list[str] = []
    for row in report.rows:
        cells = [
            styled_cell(row.sno),
            styled_cell(row.subject_name, text=True),
        ]
        cells += [styled_cell(row.grades.get(g, "")) for g in _GRADE_COLS]
        cells += [
            styled_cell(row.gpa),
            competency_cell(row.competency, row.gpa),
            styled_cell(row.rank),
        ]
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    for _label, values in report.totals.items():
        cells = "".join(styled_cell(v) for v in values)
        body_rows.append(f'<tr class="total">{cells}</tr>')
    table = (
        '<table class="tmpl">'
        f"{_thead(report.column_headers)}"
        "<tbody>" + "".join(body_rows) + "</tbody>"
        "</table>"
    )
    return document_html(report.meta, banner_html(report.meta) + table, compact=True)
