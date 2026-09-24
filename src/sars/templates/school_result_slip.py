"""Single-school result-slip template.

Serves the ``school_result_slip`` report type. The slip prints the school
identity, a division-performance summary, the full candidate list (name / sex /
aggregate / division / position / detailed subject results) and a set of
school- and subject-level performance summary tables. All fixed headings are
chrome; the school identity, the counts and every candidate row are data.

Expected data shape: a :class:`~sars.schema.SchoolResultSlip` with

* ``meta``             - :class:`~sars.schema.ReportMeta`;
* ``centre_no`` / ``school_name`` - the school identity line;
* ``division_summary`` - :class:`~sars.schema.DivisionSummaryRow` (a sex row and
  its ``{division_label: count}`` map);
* ``students``         - :class:`~sars.schema.StudentRow` (cno, name, sex,
  aggregate, division, position, detailed_subjects);
* ``performance``      - :class:`~sars.schema.PerformanceTable` blocks captured
  header-driven (registration counts, per-subject grade breakdown, ranking).
"""

from __future__ import annotations

from ..schema import PerformanceTable, SchoolResultSlip
from .base import (
    banner_html,
    document_html,
    esc,
    styled_cell,
)

#: Candidate-list column headings (chrome).
_STUDENT_HEADERS = ("CNO", "CANDIDATE FULL NAME", "SEX", "AGGT", "DIV", "POS", "DETAILED SUBJECTS")


def _division_summary_html(slip: SchoolResultSlip) -> str:
    if not slip.division_summary:
        return ""
    # Union of division labels across rows, in first-seen order.
    labels: list[str] = []
    for drow in slip.division_summary:
        for label in drow.divisions:
            if label not in labels:
                labels.append(label)
    head = "<th>SEX</th>" + "".join(f"<th>{esc(lbl)}</th>" for lbl in labels)
    rows: list[str] = []
    for drow in slip.division_summary:
        cells = styled_cell(drow.sex)
        cells += "".join(styled_cell(drow.divisions.get(lbl, "")) for lbl in labels)
        rows.append(f"<tr>{cells}</tr>")
    return (
        '<table class="tmpl">'
        f"<thead><tr>{head}</tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody>"
        "</table>"
    )


def _students_html(slip: SchoolResultSlip) -> str:
    head = "".join(
        (
            f'<th class="text">{esc(h)}</th>'
            if h in ("CANDIDATE FULL NAME", "DETAILED SUBJECTS")
            else f"<th>{esc(h)}</th>"
        )
        for h in _STUDENT_HEADERS
    )
    rows: list[str] = []
    for st in slip.students:
        fields = [
            (st.cno, False),
            (st.name, True),
            (st.sex, False),
            (st.aggregate, False),
            (st.division, False),
            (st.position, False),
            (st.detailed_subjects, True),
        ]
        cells = "".join(styled_cell(value, text=left) for value, left in fields)
        rows.append(f"<tr>{cells}</tr>")
    return (
        '<table class="tmpl">'
        f"<thead><tr>{head}</tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody>"
        "</table>"
    )


def _performance_html(table: PerformanceTable) -> str:
    headers = table.column_headers
    leaves = [h.split(" / ")[-1] if h else "" for h in headers]
    head = "".join(f"<th>{esc(leaf)}</th>" for leaf in leaves)
    rows: list[str] = []
    for prow in table.rows:
        cells = "".join(
            styled_cell(prow.values.get(headers[i], prow.values.get(leaves[i], "")))
            for i in range(len(headers))
        )
        rows.append(f"<tr>{cells}</tr>")
    return (
        '<table class="tmpl">'
        f"<thead><tr>{head}</tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody>"
        "</table>"
    )


def render_school_result_slip(slip: SchoolResultSlip) -> str:
    """Render a :class:`~sars.schema.SchoolResultSlip` to a full HTML doc."""
    identity = ""
    if slip.centre_no or slip.school_name:
        identity = f"{slip.centre_no} - {slip.school_name}".strip(" -")
    body = banner_html(slip.meta, extra_lines=(identity,) if identity else ())
    body += _division_summary_html(slip)
    body += _students_html(slip)
    body += "".join(_performance_html(p) for p in slip.performance)
    return document_html(slip.meta, body)
