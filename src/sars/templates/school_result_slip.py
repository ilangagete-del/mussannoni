"""Single-school result-slip template - SELF-CONTAINED and FAITHFUL.

Serves the ``school_result_slip`` report type. The slip prints the school
identity, a division-performance summary, the full candidate list and a set of
school- and subject-level performance tables. This template OWNS its structure
and its complete inline styling, including the slip's recovered pale panel wash
(``#92cddc``) that the report type paints behind its content as fixed chrome.
It shares no cross-report CSS constant.

DATA IS DATA: all headings / the panel wash are chrome; the school identity, the
counts and every candidate row are data.
"""

from __future__ import annotations

from ..schema import PerformanceTable, SchoolResultSlip
from .base import banner_html, orientation_for
from .styling import Sheet, document, esc, fit_scale

#: Candidate-list column headings (chrome).
_STUDENT_HEADERS = ("CNO", "CANDIDATE FULL NAME", "SEX", "AGGT", "DIV", "POS", "DETAILED SUBJECTS")

#: The slip's recovered panel wash (fixed chrome for this report type).
_PANEL_BG = "#92cddc"

_PT_DATA = 6.7
_PT_ROW = 9.4
_PT_BANNER = 8.0


def _style(orientation: str) -> Sheet:
    s = fit_scale(orientation)
    px = lambda pt: f"{pt * s:.2f}pt"  # noqa: E731
    sheet = Sheet()
    sheet.extend(f"""
body{{margin:0;color:#000;font-family:Arial, Helvetica, sans-serif}}
.report{{padding:{px(6)} {px(8)};background-color:{_PANEL_BG}}}
.banner{{text-align:center;font-weight:700;font-size:{px(_PT_BANNER)};line-height:1.4}}
.banner .title{{margin-top:{px(6)};font-size:{px(_PT_BANNER)}}}
table.rs{{border-collapse:collapse;table-layout:fixed;width:100%;
        border-spacing:0;margin-top:{px(6)};background-color:#fff}}
table.rs th,table.rs td{{border:0.4pt solid #000;padding:0 1pt;
        text-align:center;vertical-align:middle;overflow:visible;
        font-size:{px(_PT_DATA)};line-height:{px(_PT_ROW)};
        white-space:normal;overflow-wrap:normal;word-break:keep-all}}
table.rs th{{font-weight:700}}
table.rs td.text,table.rs th.text{{text-align:left}}
""")
    return sheet


def _division_summary_html(slip: SchoolResultSlip) -> str:
    if not slip.division_summary:
        return ""
    labels: list[str] = []
    for drow in slip.division_summary:
        for label in drow.divisions:
            if label not in labels:
                labels.append(label)
    head = "<th>SEX</th>" + "".join(f"<th>{esc(lbl)}</th>" for lbl in labels)
    rows: list[str] = []
    for drow in slip.division_summary:
        cells = f"<td>{esc(drow.sex)}</td>"
        cells += "".join(f"<td>{esc(drow.divisions.get(lbl, ''))}</td>" for lbl in labels)
        rows.append(f"<tr>{cells}</tr>")
    return (
        '<table class="rs">'
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
        cells = "".join(
            f'<td class="text">{esc(value)}</td>' if left else f"<td>{esc(value)}</td>"
            for value, left in fields
        )
        rows.append(f"<tr>{cells}</tr>")
    return (
        '<table class="rs">'
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
            f"<td>{esc(prow.values.get(headers[i], prow.values.get(leaves[i], '')))}</td>"
            for i in range(len(headers))
        )
        rows.append(f"<tr>{cells}</tr>")
    return (
        '<table class="rs">'
        f"<thead><tr>{head}</tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody>"
        "</table>"
    )


def render_school_result_slip(slip: SchoolResultSlip) -> str:
    """Render a :class:`~sars.schema.SchoolResultSlip` to a standalone doc."""
    identity = ""
    if slip.centre_no or slip.school_name:
        identity = f"{slip.centre_no} - {slip.school_name}".strip(" -")
    orientation = orientation_for(slip.meta)
    sheet = _style(orientation)
    body = '<section class="report">'
    body += banner_html(slip.meta, extra_lines=(identity,) if identity else ())
    body += _division_summary_html(slip)
    body += _students_html(slip)
    body += "".join(_performance_html(p) for p in slip.performance)
    body += "</section>"
    return document(
        title=slip.meta.title or slip.meta.name,
        orientation=orientation,
        sheet=sheet,
        body=body,
    )
