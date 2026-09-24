"""Fixed-layout single-school result-slip report (landscape Letter, 13 pages).

Serves the ``school_result_slip`` report type.  Like
:mod:`sars.templates.schools_rank`, this renderer is FIXED-LAYOUT and fully
self-contained: it emits the reference's OWN US-Letter page box
(``792pt 612pt``) and the reference's own 13-page pagination instead of the old
A4 reflow.  It owns its complete inline styling, including the slip's recovered
pale panel wash (``#92cddc``) that the report type paints behind its content as
fixed chrome, and shares no cross-report CSS constant.

Recovered reference structure (via :func:`sars.extract.extract_document`):

* Page 1  - masthead (5 centred lines) + ``DIVISION PERFORMANCE SUMMARY`` title
  + the F/M/T division-summary table + the candidate-list header and the first
  25 candidates, all inside the pale ``#92cddc`` panel.
* Pages 2-11 - the candidate list continues, 38 rows on pages 2-10 and 13 on
  page 11 (380 candidates total), with the panel painted as a thin cyan strip
  down each margin the way the reference does.
* Page 12 - a second pale panel carrying the examination-centre summary, the
  registration/division summary and the subject-performance-and-ranking table.
* Page 13 - the subject grading-performance summary table.

DATA IS DATA: the masthead / headings / the panel wash are chrome; the school
identity, the counts and every candidate row are data.  Row pitch is expressed
as ``line-height`` on the cells (not a ``<tr>`` height) so WeasyPrint drops no
candidate row across the 13 pages.
"""

from __future__ import annotations

from ..schema import PerformanceTable, SchoolResultSlip
from .base import banner_lines, competency_background
from .styling import Sheet, esc

# --------------------------------------------------------------------------- #
# Recovered reference colours (fixed chrome for this report type).
# --------------------------------------------------------------------------- #
_PANEL_BG = "#92cddc"   # the pale panel wash behind the content
_CREAM_BG = "#ffffcc"   # the cream fill of the candidate rows / summary values
_REG_BG = "#eeece1"     # CNO header cell
_POS_BG = "#fde9d9"     # POS / rank-head cells
_DIVHEAD_BG = "#d2fce6" # division-summary I..IV headers
_ZEROHEAD_BG = "#e6b8b7"  # division-summary "0" header

# --------------------------------------------------------------------------- #
# Recovered reference geometry, in points (source page is 792 x 612 Letter).
# --------------------------------------------------------------------------- #
# Page 1 panel wash: (x0, y0, x1, y1).
_PANEL1 = (17.4, 54.2, 764.5, 549.7)
# Page 12 panel wash.
_PANEL12 = (17.4, 54.2, 764.5, 389.5)

# Masthead: five centred bold lines starting near the panel top.
_MASTHEAD_TOP = 52.0
_MASTHEAD_PT = 8.3
_MASTHEAD_PITCH = 13.0

_SUMMARY_TITLE_TOP = 128.0  # "DIVISION PERFORMANCE SUMMARY" heading

# Division-summary table origin + column widths (SEX + I,II,III,IV,0).
_DIVSUM_X = 136.9
_DIVSUM_Y = 146.2
_DIVSUM_COLS = (80.4, 25.8, 25.9, 25.8, 25.8, 28.9)
_DIVSUM_ROW = 11.45  # four rows of ~11.4pt

# Candidate list.  Page 1 starts lower (below the summary); the header row is
# tall; continuation pages start near the top margin.  Both pages model the
# reference's own 9-column lattice so the recovered shape matches cell-for-cell.
_CAND_Y_P1 = 204.5
_CAND_Y_CONT = 54.1
_CAND_HEAD_H = 21.0
_CAND_ROW = 13.05
# Page 1: table origin 44.2; NAME and DETAILED each span two lattice columns.
_CAND_X_P1 = 44.2
_CAND_COLS_P1 = (46.5, 46.2, 80.4, 25.8, 25.9, 25.8, 25.8, 28.9, 399.8)
# Continuation pages: table origin 17.4; a thin cyan margin column brackets each
# side (17.4->44.2 and 749.3->764.5), matching the reference lattice.
_CAND_X_CONT = 17.4
_CAND_COLS_CONT = (26.8, 46.5, 126.6, 25.8, 25.9, 25.8, 25.8, 428.7, 15.2)

# Exact recovered per-page candidate split (sum = 380 -> 11 candidate pages).
_CAND_SPLIT: tuple[int, ...] = (25, 38, 38, 38, 38, 38, 38, 38, 38, 38, 13)

# Performance block (pages 12-13) origins.
_PERF_X = 44.3
_PERF12_SUMMARY_Y = 75.0    # first performance table origin on page 12
_PERF13_Y = 54.2            # grading-performance summary origin on page 13
_PERF_ROW = 11.4

_STUDENT_HEADERS = ("CNO", "CANDIDATE FULL NAME", "SEX", "AGGT", "DIV", "POS", "DETAILED SUBJECTS")


def _style() -> Sheet:
    """Return this report's complete, independent print stylesheet.

    Every CSS rule is emitted on ONE physical line: :meth:`styling.Sheet.extend`
    dedups per line and silently truncates a multi-line rule that shares a
    continuation line with another (the bug FEAT-004 found), so keeping each
    rule inline avoids dropping the table rule.
    """
    sheet = Sheet()
    sheet.add('html,body{margin:0;padding:0;width:792pt;height:612pt;background:#fff}')
    sheet.add('body{color:#000;font-family:Arial,"Liberation Sans",Helvetica,sans-serif}')
    sheet.add('.report{position:relative;width:792pt;height:612pt;overflow:hidden}')
    sheet.add('.report + .report{page-break-before:always}')
    sheet.add('.panel{position:absolute;background:' + _PANEL_BG + '}')
    sheet.add('.masthead{position:absolute;left:0;width:792pt;text-align:center;font-weight:700;'
              f'font-size:{_MASTHEAD_PT:.2f}pt;line-height:{_MASTHEAD_PITCH:.2f}pt}}')
    sheet.add('.divtitle{position:absolute;left:0;width:792pt;text-align:center;font-weight:700;'
              f'font-size:{_MASTHEAD_PT:.2f}pt}}')
    sheet.add('table.rs{position:absolute;border-collapse:collapse;table-layout:fixed;'
              'border-spacing:0;margin:0;padding:0}')
    sheet.add('table.rs col{box-sizing:border-box}')
    sheet.add('table.rs th,table.rs td{box-sizing:border-box;border:0.4pt solid #000;'
              'padding:0 0.6pt;text-align:center;vertical-align:middle;overflow:hidden;'
              'white-space:nowrap;color:#000}')
    sheet.add('table.rs td.text,table.rs th.text{text-align:left}')
    # Candidate list.
    sheet.add(f'table.cand.p1{{left:{_CAND_X_P1:.2f}pt;top:{_CAND_Y_P1:.2f}pt;'
              f'width:{sum(_CAND_COLS_P1):.2f}pt}}')
    sheet.add(f'table.cand.cont{{left:{_CAND_X_CONT:.2f}pt;top:{_CAND_Y_CONT:.2f}pt;'
              f'width:{sum(_CAND_COLS_CONT):.2f}pt}}')
    sheet.add(f'table.cand th{{font-size:7.3pt;font-weight:700;'
              f'line-height:{_CAND_HEAD_H - 0.8:.2f}pt;background:{_CREAM_BG}}}')
    sheet.add(f'table.cand td{{font-size:6.7pt;font-weight:400;'
              f'line-height:{_CAND_ROW - 0.55:.2f}pt;background:{_CREAM_BG}}}')
    # Detailed subjects stay on ONE line (as the reference does) so long rows do
    # not wrap and push the rest of the page down; a hair-smaller font keeps the
    # longest entry inside its 428pt column without clipping any token.
    sheet.add('table.cand td.det{white-space:nowrap;overflow:visible;font-size:6.3pt}')
    sheet.add('table.cand th.cno{background:' + _REG_BG + '}')
    sheet.add('table.cand th.pos{background:' + _POS_BG + '}')
    # The bracketing margin columns on continuation pages carry the panel wash.
    sheet.add('table.cand td.margin,table.cand th.margin{background:' + _PANEL_BG
              + ';border:0;padding:0}')
    # Division summary.
    sheet.add(f'table.divsum{{left:{_DIVSUM_X:.2f}pt;top:{_DIVSUM_Y:.2f}pt;'
              f'width:{sum(_DIVSUM_COLS):.2f}pt}}')
    sheet.add(f'table.divsum th,table.divsum td{{font-size:7.3pt;'
              f'line-height:{_DIVSUM_ROW - 0.8:.2f}pt;background:{_CREAM_BG}}}')
    sheet.add('table.divsum th.sex{background:' + _CREAM_BG + ';font-weight:700}')
    sheet.add('table.divsum th.div{background:' + _DIVHEAD_BG + ';font-weight:700}')
    sheet.add('table.divsum th.zero{background:' + _ZEROHEAD_BG + ';font-weight:700}')
    sheet.add('table.divsum td.rowlabel{font-weight:700}')
    sheet.add('table.divsum td.total{font-weight:700}')
    # Performance tables (pages 12-13).
    sheet.add(f'table.perf{{left:{_PERF_X:.2f}pt;width:{749.3 - _PERF_X:.2f}pt}}')
    sheet.add(f'table.perf th,table.perf td{{font-size:6.7pt;line-height:{_PERF_ROW - 0.8:.2f}pt;'
              'background:' + _CREAM_BG + '}')
    sheet.add('table.perf th{font-weight:700;white-space:normal}')
    # Text columns (subject names, competency labels) carry long values; let them
    # wrap / overhang rather than clip so no recovered glyph is lost.
    sheet.add('table.perf td.text,table.perf th.text{text-align:left;white-space:normal;'
              'overflow:visible;word-break:break-word}')
    return sheet


def _colgroup(widths: tuple[float, ...]) -> str:
    return "<colgroup>" + "".join(f'<col style="width:{w:.2f}pt">' for w in widths) + "</colgroup>"


# --------------------------------------------------------------------------- #
# Page 1 chrome
# --------------------------------------------------------------------------- #
def _panel(box: tuple[float, float, float, float]) -> str:
    x0, y0, x1, y1 = box
    return (f'<div class="panel" style="left:{x0:.2f}pt;top:{y0:.2f}pt;'
            f'width:{x1 - x0:.2f}pt;height:{y1 - y0:.2f}pt"></div>')


def _masthead_html(slip: SchoolResultSlip) -> str:
    identity = f"{slip.centre_no} - {slip.school_name}".strip(" -")
    lines = banner_lines(slip.meta, extra_lines=(identity,) if identity else ())
    top = _MASTHEAD_TOP
    out = []
    for line in lines:
        out.append(f'<div class="masthead" style="top:{top:.2f}pt">{line}</div>')
        top += _MASTHEAD_PITCH
    out.append(f'<div class="divtitle" style="top:{_SUMMARY_TITLE_TOP:.2f}pt">'
               "DIVISION PERFORMANCE SUMMARY</div>")
    return "".join(out)


def _division_summary_html(slip: SchoolResultSlip) -> str:
    if not slip.division_summary:
        return ""
    labels: list[str] = []
    for drow in slip.division_summary:
        for label in drow.divisions:
            if label not in labels:
                labels.append(label)
    head = '<th class="sex">SEX</th>'
    for lbl in labels:
        cls = "zero" if lbl == "0" else "div"
        head += f'<th class="{cls}">{esc(lbl)}</th>'
    rows = [f"<tr>{head}</tr>"]
    for drow in slip.division_summary:
        is_total = drow.sex.strip().upper() == "T"
        rc = ' class="rowlabel total"' if is_total else ' class="rowlabel"'
        cells = f"<td{rc}>{esc(drow.sex)}</td>"
        vc = ' class="total"' if is_total else ""
        cells += "".join(f"<td{vc}>{esc(drow.divisions.get(lbl, ''))}</td>" for lbl in labels)
        rows.append(f"<tr>{cells}</tr>")
    return ('<table class="rs divsum">' + _colgroup(_DIVSUM_COLS)
            + "".join(rows) + "</table>")


# --------------------------------------------------------------------------- #
# Candidate list
# --------------------------------------------------------------------------- #
def _candidate_head() -> str:
    # Page-1 lattice: NAME and DETAILED each span two columns (colspan 2).
    return (
        "<tr>"
        '<th class="cno">CNO</th>'
        '<th class="text" colspan="2">CANDIDATE FULL NAME</th>'
        "<th>SEX</th><th>AGGT</th><th>DIV</th>"
        '<th class="pos">POS</th>'
        '<th class="text" colspan="2">DETAILED SUBJECTS</th>'
        "</tr>"
    )


def _candidate_body_row(st, *, page1: bool) -> str:
    """One candidate row on the reference's 9-column lattice.

    Page 1 has no margin columns but NAME / DETAILED span two lattice columns;
    continuation pages carry a cyan margin column on each side.
    """
    if page1:
        name = f'<td class="text" colspan="2">{esc(st.name)}</td>'
        det = f'<td class="text det" colspan="2">{esc(st.detailed_subjects)}</td>'
    else:
        name = f'<td class="text">{esc(st.name)}</td>'
        det = f'<td class="text det">{esc(st.detailed_subjects)}</td>'
    core = (
        f"<td>{esc(st.cno)}</td>"
        f"{name}"
        f"<td>{esc(st.sex)}</td><td>{esc(st.aggregate)}</td><td>{esc(st.division)}</td>"
        f"<td>{esc(st.position)}</td>"
        f"{det}"
    )
    if page1:
        return f"<tr>{core}</tr>"
    return f'<tr><td class="margin">&#160;</td>{core}<td class="margin">&#160;</td></tr>'


def _candidate_table(body_rows: str, *, page1: bool) -> str:
    if page1:
        return ('<table class="rs cand p1">' + _colgroup(_CAND_COLS_P1)
                + f"<thead>{_candidate_head()}</thead>"
                + f"<tbody>{body_rows}</tbody></table>")
    return ('<table class="rs cand cont">' + _colgroup(_CAND_COLS_CONT)
            + f"<tbody>{body_rows}</tbody></table>")


# --------------------------------------------------------------------------- #
# Performance tables (pages 12-13)
# --------------------------------------------------------------------------- #
def _perf_thead(paths: list[str]) -> str:
    """Rebuild the grouped header band from ``/``-separated column label paths."""
    if not paths:
        return ""
    split = [p.split(" / ") if p else [""] for p in paths]
    depth = max(len(s) for s in split)
    real_len = [len(s) for s in split]
    padded = [s + [s[-1]] * (depth - len(s)) for s in split]
    n = len(padded)
    covered = [[False] * n for _ in range(depth)]
    rows_html: list[str] = []
    for r in range(depth):
        cells: list[str] = []
        c = 0
        while c < n:
            if covered[r][c]:
                c += 1
                continue
            prefix = padded[c][: r + 1]
            colspan = 1
            while (c + colspan < n and padded[c + colspan][: r + 1] == prefix
                   and not covered[r][c + colspan]):
                colspan += 1
            rowspan = depth - r if real_len[c] <= r + 1 else 1
            attrs = ""
            if colspan > 1:
                attrs += f' colspan="{colspan}"'
            if rowspan > 1:
                attrs += f' rowspan="{rowspan}"'
            cells.append(f"<th{attrs}>{esc(padded[c][r])}</th>")
            for rr in range(r, r + rowspan):
                for cc in range(c, c + colspan):
                    covered[rr][cc] = True
            c += colspan
        rows_html.append("<tr>" + "".join(cells) + "</tr>")
    return "".join(rows_html)


def _perf_leaves(paths: list[str]) -> list[str]:
    return [p.split(" / ")[-1] if p else "" for p in paths]


def _is_text_leaf(leaf: str) -> bool:
    up = leaf.upper()
    return any(k in up for k in ("NAME", "SUBJECT", "REGION", "COUNCIL", "AVERAGE",
                                 "RANKING", "PASSED", "GPA PERFORMANCE", "LEVEL",
                                 "COMPETENCY", "COMPENTENCY"))


def _perf_body(table: PerformanceTable) -> str:
    paths = table.column_headers
    leaves = _perf_leaves(paths)
    comp_idx = next((i for i, lf in enumerate(leaves) if "COMPETENCY" in lf.upper()
                     or "COMPENTENCY" in lf.upper()), None)
    gpa_idx = next((i for i, lf in enumerate(leaves) if lf.upper() == "GPA"), None)
    rows: list[str] = []
    for prow in table.rows:
        cells = []
        i = 0
        n = len(paths)
        while i < n:
            path = paths[i]
            leaf = leaves[i]
            # A leaf whose full path repeats on adjacent columns is one merged
            # (colspan) cell in the reference; emit its value ONCE so the token
            # is not duplicated / glued to its neighbour (e.g. GPA, COMPETENCY).
            span = 1
            while i + span < n and paths[i + span] == path:
                span += 1
            value = prow.values.get(path, prow.values.get(leaf, ""))
            text_col = _is_text_leaf(leaf)
            style = ""
            if i == comp_idx:
                gpa = ""
                if gpa_idx is not None:
                    gpa = prow.values.get(paths[gpa_idx], prow.values.get(leaves[gpa_idx], ""))
                bg = competency_background(value, gpa)
                if bg:
                    style = f' style="background-color:{bg}"'
            cls = ' class="text"' if text_col else ""
            span_attr = f' colspan="{span}"' if span > 1 else ""
            cells.append(f"<td{cls}{span_attr}{style}>{esc(value)}</td>")
            i += span
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return "".join(rows)


def _perf_weight(leaf: str) -> float:
    up = leaf.upper()
    if "COMPETENCY" in up or "COMPENTENCY" in up or "LEVEL" in up:
        return 6.0
    if "SUBJECT NAME" in up or up == "NAME":
        return 5.0
    if "RANK" in up:
        return 2.4
    if "CODE" in up:
        return 1.6
    return 1.5


def _perf_colgroup(paths: list[str]) -> str:
    leaves = _perf_leaves(paths)
    weights = [_perf_weight(lf) for lf in leaves]
    total = sum(weights) or 1.0
    cols = "".join(f'<col style="width:{w / total * 100:.3f}%">' for w in weights)
    return f"<colgroup>{cols}</colgroup>"


def _perf_table(table: PerformanceTable, *, top: float) -> str:
    thead = _perf_thead(table.column_headers)
    body = _perf_body(table)
    return (f'<table class="rs perf" style="top:{top:.2f}pt">'
            + _perf_colgroup(table.column_headers)
            + (f"<thead>{thead}</thead>" if thead else "")
            + f"<tbody>{body}</tbody></table>")


# --------------------------------------------------------------------------- #
# Document assembly
# --------------------------------------------------------------------------- #
def _document(title: str, sheet: Sheet, body: str) -> str:
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{esc(title)}</title>\n<style>\n@page{{size:792pt 612pt;margin:0}}\n"
        f"{sheet.css()}\n</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def _reconcile(counts: list[int], total: int) -> list[int]:
    counts = [c for c in counts if c > 0] or [total]
    placed = sum(counts)
    if placed < total:
        counts[-1] += total - placed
    elif placed > total:
        overflow = placed - total
        while overflow and counts:
            take = min(overflow, counts[-1])
            counts[-1] -= take
            overflow -= take
            if counts[-1] == 0 and len(counts) > 1:
                counts.pop()
    return [c for c in counts if c > 0] or [total]


def render_school_result_slip(slip: SchoolResultSlip) -> str:
    """Render a :class:`~sars.schema.SchoolResultSlip` to a standalone doc."""
    sheet = _style()
    sections: list[str] = []

    # --- candidate pages (1..N) --------------------------------------- #
    n_students = len(slip.students)
    counts = _reconcile(list(_CAND_SPLIT), n_students)
    cursor = 0
    for pi, count in enumerate(counts):
        page1 = pi == 0
        chunk = "".join(
            _candidate_body_row(st, page1=page1)
            for st in slip.students[cursor:cursor + count]
        )
        cursor += count
        if page1:
            inner = (_panel(_PANEL1) + _masthead_html(slip)
                     + _division_summary_html(slip)
                     + _candidate_table(chunk, page1=True))
        else:
            inner = _candidate_table(chunk, page1=False)
        sections.append(f'<section class="report">{inner}</section>')

    # --- performance pages (12-13) ------------------------------------ #
    # The reference prints its school/subject performance tables on page 12
    # (inside a second pale panel) and continues onto page 13, matching the
    # recovered layout: the registration/division summary and the subject
    # performance-and-ranking table on page 12, the subject grading summary on
    # page 13.  Tables are stacked top-to-bottom at the recovered origins.
    if slip.performance:
        perf = list(slip.performance)
        page12 = _panel(_PANEL12)
        y = _PERF12_SUMMARY_Y
        for tbl in perf[:2]:
            page12 += _perf_table(tbl, top=y)
            # Advance below this table (header band + data rows + a small gap).
            y += (len(tbl.rows) + 3) * _PERF_ROW + 16
        sections.append(f'<section class="report">{page12}</section>')

        if len(perf) > 2:
            page13 = "".join(_perf_table(tbl, top=_PERF13_Y) for tbl in perf[2:])
            sections.append(f'<section class="report">{page13}</section>')

    body = "".join(sections)
    return _document(slip.meta.title or slip.meta.name, sheet, body)
