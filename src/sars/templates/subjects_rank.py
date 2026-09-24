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
    TemplatePool,
    banner_html,
    competency_cell,
    document_html,
    header_cell,
    orientation_for,
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

    Every ``<td>`` carries the recovered font / colour / fill and row pitch keyed
    by its physical column index (0=S/NO., 1=SUBJECT, 2-11=the grade / summary
    columns, 12=GPA, 13=COMPETENCY, 14=RANK), so the report reproduces its own
    styling cell-by-cell.
    """
    pool = TemplatePool(orientation_for(report.meta))
    body_rows: list[str] = []
    for row in report.rows:
        st = row.styles

        def s(col: int, _st: dict = st) -> object:
            return _st.get(str(col))

        p = row.pitch
        cells = [
            styled_cell(pool, row.sno, s(0), p),
            styled_cell(pool, row.subject_name, s(1), p, text=True),
        ]
        cells += [
            styled_cell(pool, row.grades.get(g, ""), s(2 + i), p)
            for i, g in enumerate(_GRADE_COLS)
        ]
        cells += [
            styled_cell(pool, row.gpa, s(12), p),
            competency_cell(row.competency, row.gpa, pool=pool, style=s(13), pitch=p),
            styled_cell(pool, row.rank, s(14), p),
        ]
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    for label, values in report.totals.items():
        styles = report.total_styles.get(label, [])
        pitch = report.total_pitch.get(label, 0.0)
        cells = "".join(
            styled_cell(pool, v, styles[c] if c < len(styles) else None, pitch)
            for c, v in enumerate(values)
        )
        body_rows.append(f'<tr class="total">{cells}</tr>')
    table = (
        '<table class="tmpl">'
        f"{_thead(report.column_headers)}"
        "<tbody>" + "".join(body_rows) + "</tbody>"
        "</table>"
    )
    return document_html(report.meta, banner_html(report.meta) + table, compact=True, pool=pool)
