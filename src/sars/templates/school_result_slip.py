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

from ..schema import CellStyle, PerformanceTable, SchoolResultSlip
from .base import (
    TemplatePool,
    banner_html,
    document_html,
    esc,
    orientation_for,
    styled_cell,
)

#: Candidate-list column headings (chrome).
_STUDENT_HEADERS = ("CNO", "CANDIDATE FULL NAME", "SEX", "AGGT", "DIV", "POS", "DETAILED SUBJECTS")


def _division_summary_html(slip: SchoolResultSlip, pool: TemplatePool) -> str:
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
        # DivisionSummaryRow styles are keyed by "sex" or division label.
        st = drow.styles
        cells = styled_cell(pool, drow.sex, st.get("sex") if st else None, drow.pitch)
        cells += "".join(
            styled_cell(
                pool,
                drow.divisions.get(lbl, ""),
                st.get(lbl) if st else None,
                drow.pitch,
            )
            for lbl in labels
        )
        rows.append(f"<tr>{cells}</tr>")
    return (
        '<table class="tmpl">'
        f"<thead><tr>{head}</tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody>"
        "</table>"
    )


def _student_style(st_styles: dict, keys: list[str], nth: int) -> CellStyle | None:
    """Pick the recovered style for the ``nth`` emitted student cell.

    Candidate-row styles are keyed by physical column index (``extract_data``'s
    ``_row_styles``); the CNO and NAME sit at columns 0 and 1, and the remaining
    emitted cells (SEX / AGGT / DIV / POS / DETAILED) map onto the row's further
    occupied columns in order. This keeps every cell's recovered pitch / font
    without needing to re-derive the exact source column of each field.
    """
    if not st_styles:
        return None
    if nth == 0:
        return st_styles.get("0")
    if nth == 1:
        return st_styles.get("1")
    trailing = [k for k in keys if k not in ("0", "1")]
    idx = nth - 2
    if 0 <= idx < len(trailing):
        return st_styles.get(trailing[idx])
    return None


def _students_html(slip: SchoolResultSlip, pool: TemplatePool) -> str:
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
        keys = sorted((st.styles or {}), key=lambda x: int(x) if x.isdigit() else 0)
        p = st.pitch
        fields = [
            (st.cno, False),
            (st.name, True),
            (st.sex, False),
            (st.aggregate, False),
            (st.division, False),
            (st.position, False),
            (st.detailed_subjects, True),
        ]
        cells = "".join(
            styled_cell(pool, value, _student_style(st.styles, keys, i), p, text=left)
            for i, (value, left) in enumerate(fields)
        )
        rows.append(f"<tr>{cells}</tr>")
    return (
        '<table class="tmpl">'
        f"<thead><tr>{head}</tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody>"
        "</table>"
    )


def _performance_html(table: PerformanceTable, pool: TemplatePool) -> str:
    headers = table.column_headers
    leaves = [h.split(" / ")[-1] if h else "" for h in headers]
    head = "".join(f"<th>{esc(leaf)}</th>" for leaf in leaves)
    rows: list[str] = []
    for prow in table.rows:
        cells = "".join(
            styled_cell(
                pool,
                prow.values.get(headers[i], prow.values.get(leaves[i], "")),
                (prow.styles.get(headers[i], prow.styles.get(leaves[i])) if prow.styles else None),
                prow.pitch,
            )
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
    pool = TemplatePool(orientation_for(slip.meta))
    identity = ""
    if slip.centre_no or slip.school_name:
        identity = f"{slip.centre_no} - {slip.school_name}".strip(" -")
    body = banner_html(slip.meta, extra_lines=(identity,) if identity else ())
    body += _division_summary_html(slip, pool)
    body += _students_html(slip, pool)
    body += "".join(_performance_html(p, pool) for p in slip.performance)
    return document_html(slip.meta, body, pool=pool)
