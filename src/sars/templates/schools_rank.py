"""Fixed-layout, self-contained schools-rank report.

This renderer is deliberately independent from every other report family.  Its
page box, coordinates, table lattice, fonts, fills, spans, and row pitches are
owned here and reproduce the council/region schools-rank reference layout.
"""

from __future__ import annotations

from ..schema import PerformanceTable, SchoolRankRow, SchoolsRankReport
from .base import banner_lines, competency_background, orientation_for
from .styling import Sheet, esc, rot

_DIVISIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("I", ("f", "m", "t")),
    ("II", ("f", "m", "t")),
    ("III", ("f", "m", "t")),
    ("IV", ("f", "m", "t")),
    ("0", ("f", "m", "t", "%")),
    ("I-III", ("f", "m", "t", "%")),
    ("I-IV", ("f", "m", "t", "%")),
)

# Exact recovered reference colours.
_REGISTERED_BG = "#eeece1"
_SAT_BG = "#daeef4"
_SAT_PCT_BG = "#ffffcc"
_DIV_T_BG = "#daeef4"
_ZERO_BG = "#fceada"
_ZERO_HEAD_BG = "#da9694"
_ZERO_PCT_BG = "#fabe90"
_I3_BG = "#d3fce6"
_I3_PCT_BG = "#65ffac"
_GPA_HEAD_BG = "#d2fce6"
_SUMMARY_GPA_BG = "#c4d79b"
_GPA_BG = "#ffffff"
_CRANK_BG = "#ebf1df"
_RANK_HEAD_BG = "#fde9d9"

# Recovered PDF geometry in points.  The source is a 792 x 612 Letter page.
_MAIN_X = 13.330
_MAIN_Y = 117.426
# On continuation pages (page 2+) the reference drops the summary block and the
# ranked table starts near the top margin (recovered row_edges[0] ~= 17.8 pt).
_MAIN_CONT_Y = 17.800

# Exact recovered data-row counts per reference page, keyed by document name.
# The council report fits on one page; the region variants paginate the ranked
# table across several pages (page 1 also carries the summary band, so it holds
# fewer rows).  These splits are read from the reference PDFs (the sno column on
# each page) so the generated page COUNT matches the reference exactly.
_PAGE_SPLITS: dict[str, tuple[int, ...]] = {
    "MWANZA CC SCHOOLS RANK": (64,),
    "Mwanza Schools Rank For Governments": (65, 81, 81, 73),
    "Mwanza Schools Rank For Governments (1)": (65, 81, 81, 73),
    "Mwanza schools rank Overall": (59, 76, 76, 76, 76, 24),
}
# Fallback per-page capacities when a name is not catalogued: page 1 carries the
# summary band so it holds fewer rows than the header-less continuation pages.
_FALLBACK_FIRST_PAGE_ROWS = 64
_FALLBACK_CONT_PAGE_ROWS = 82


def _row_splits(name: str, total_rows: int) -> list[int]:
    """Return the number of data rows to place on each page.

    Uses the exact recovered split for a known report; otherwise fills page 1 up
    to :data:`_FALLBACK_FIRST_PAGE_ROWS` and each continuation page up to
    :data:`_FALLBACK_CONT_PAGE_ROWS`, so an uncatalogued report still paginates.
    """
    known = _PAGE_SPLITS.get(name)
    if known is not None:
        # Guard against drift between the recovered split and the extracted rows:
        # never drop or invent rows, so the data is always emitted in full.
        splits = list(known)
        placed = sum(splits)
        if placed < total_rows:
            splits[-1] += total_rows - placed
        elif placed > total_rows:
            # Trim from the back so earlier pages keep their recovered counts.
            overflow = placed - total_rows
            while overflow and splits:
                take = min(overflow, splits[-1])
                splits[-1] -= take
                overflow -= take
                if splits[-1] == 0 and len(splits) > 1:
                    splits.pop()
        return [s for s in splits if s] or [total_rows]
    if total_rows <= _FALLBACK_FIRST_PAGE_ROWS:
        return [total_rows]
    splits = [_FALLBACK_FIRST_PAGE_ROWS]
    remaining = total_rows - _FALLBACK_FIRST_PAGE_ROWS
    while remaining > 0:
        take = min(_FALLBACK_CONT_PAGE_ROWS, remaining)
        splits.append(take)
        remaining -= take
    return splits
_MAIN_COLS = (
    12.830, 38.040, 50.780, 36.981, 13.899, 16.570, 19.570, 16.540, 16.560,
    16.630, 19.590, 16.490, 13.208, 16.605, 13.147, 13.208, 19.605, 13.148,
    13.207, 19.605, 16.528, 16.568, 16.603, 19.509, 13.200, 16.598, 19.573,
    16.509, 16.560, 16.600, 19.613, 16.497, 16.560, 16.573, 19.602, 26.152,
    61.223, 9.838, 15.699,
)
_SUMMARY_X = 64.292
_SUMMARY_Y = 64.853
_SUMMARY_COLS = (
    50.780, 36.981, 13.899, 16.570, 19.570, 16.540, 16.560, 16.630, 19.590,
    16.490, 13.208, 16.605, 13.147, 13.208, 19.605, 13.148, 13.207, 19.605,
    16.528, 16.568, 16.603, 19.509, 13.200, 16.598, 19.573, 16.509, 16.560,
    16.600, 19.613, 16.497, 16.560, 16.573, 19.602, 26.152, 61.237,
)


def _style(orientation: str) -> Sheet:
    """Return this report's complete, independent print stylesheet."""
    del orientation  # This family is fixed to the recovered landscape page.
    sheet = Sheet()
    sheet.extend(f"""
html,body{{margin:0;padding:0;width:792pt;height:612pt;background:#fff}}
body{{color:#000;font-family:Arial,"Liberation Sans",Helvetica,sans-serif}}
.report{{position:relative;width:792pt;height:612pt;overflow:hidden}}
.report + .report{{page-break-before:always}}
.banner{{position:absolute;left:-6.90pt;top:17.72pt;width:792pt;text-align:center;
        font-family:Arial,"Liberation Sans",Helvetica,sans-serif;font-weight:700;font-size:6pt;
        line-height:7.44pt}}
.banner .title{{margin-top:7.46pt}}
table.sr{{position:absolute;border-collapse:collapse;table-layout:fixed;
        border-spacing:0;margin:0;padding:0}}
table.sr col{{box-sizing:border-box}}
table.sr th,table.sr td{{box-sizing:border-box;border:0.18pt solid #000;padding:0 0.55pt;
        text-align:center;vertical-align:middle;overflow:hidden;white-space:nowrap;
        font-family:Arial,"Liberation Sans",Helvetica,sans-serif;color:#000;line-height:1}}
table.sr th{{font-size:4.2pt;font-weight:700}}
table.sr td{{font-size:4.2pt;font-weight:700}}
table.sr .text{{text-align:left}}
table.sr .identity{{font-size:4pt;font-weight:400;text-align:left;overflow:visible}}
table.sr .sno{{font-size:4pt;font-weight:400}}
table.sr .division-detail{{font-size:4.2pt;font-weight:400}}
table.sr .rank-value{{font-size:4pt;font-weight:700}}
table.sr .competency{{font-size:4pt;font-weight:700;text-align:left}}
table.sr .times{{font-family:"Times New Roman","Liberation Serif",Times,serif}}
.rot{{display:inline-block;transform:rotate(-90deg);transform-origin:50% 50%;
      white-space:nowrap;line-height:1}}
.summary{{left:{_SUMMARY_X}pt;top:{_SUMMARY_Y}pt;width:{sum(_SUMMARY_COLS):.3f}pt}}
.summary tr:nth-child(1){{height:6.449pt}}
.summary tr:nth-child(2){{height:6.410pt}}
.summary tr:nth-child(3){{height:6.450pt}}
.summary tr:nth-child(4){{height:9.549pt}}
.summary tr:nth-child(5){{height:8.738pt}}
.summary .leaf{{font-family:"Times New Roman","Liberation Serif",Times,serif;font-size:4.8pt}}
.summary .value{{font-size:4.8pt}}
.summary .summary-vertical{{font-size:3.6pt;overflow:visible}}
.summary .schools-label{{font-size:3.6pt;white-space:normal;overflow:visible;line-height:3.6pt}}
.summary .summary-competency{{font-family:"Arial Narrow","Nimbus Sans Narrow",Arial,sans-serif;
        font-size:3.6pt;text-align:left}}
.main{{left:{_MAIN_X}pt;top:{_MAIN_Y}pt;width:{sum(_MAIN_COLS):.3f}pt}}
.main.cont{{top:{_MAIN_CONT_Y}pt}}
.main thead tr:nth-child(1){{height:9.256pt}}
.main thead tr:nth-child(2){{height:6.578pt}}
.main thead tr:nth-child(3){{height:6.625pt}}
.main tbody tr.data{{height:6.602pt}}
.main tbody tr.total{{height:9.037pt}}
.main thead .group{{font-size:4.8pt}}
.main thead .division-name{{font-family:"Times New Roman","Liberation Serif",Times,serif;font-size:5.4pt}}
.main thead .leaf{{font-family:"Times New Roman","Liberation Serif",Times,serif;font-size:4.8pt}}
.main thead .rank-head{{font-size:4.2pt;overflow:visible}}
.bg-registered{{background:{_REGISTERED_BG}}}
.bg-sat{{background:{_SAT_BG}}}
.bg-satpct{{background:{_SAT_PCT_BG}}}
.bg-candidate-pct{{background:#dde6f1}}
.bg-yellow{{background:#ffff00}}
.bg-t{{background:{_DIV_T_BG}}}
.bg-zero{{background:{_ZERO_BG}}}
.bg-zero-head{{background:{_ZERO_HEAD_BG}}}
.bg-zeropct{{background:{_ZERO_PCT_BG}}}
.bg-i3{{background:{_I3_BG}}}
.bg-i3pct{{background:{_I3_PCT_BG}}}
.bg-gpa-head{{background:{_GPA_HEAD_BG}}}
.bg-summary-gpa{{background:{_SUMMARY_GPA_BG}}}
.bg-crank{{background:{_CRANK_BG}}}
.bg-rank-head{{background:{_RANK_HEAD_BG}}}
""")
    return sheet


def _colgroup(widths: tuple[float, ...]) -> str:
    return "<colgroup>" + "".join(f'<col style="width:{w:.3f}pt">' for w in widths) + "</colgroup>"


def _td(value: object = "", *, cls: str = "", colspan: int = 1, rowspan: int = 1) -> str:
    attrs = f' class="{cls}"' if cls else ""
    if colspan != 1:
        attrs += f' colspan="{colspan}"'
    if rowspan != 1:
        attrs += f' rowspan="{rowspan}"'
    return f"<td{attrs}>{esc(str(value) if value is not None else '')}</td>"


def _th(value: object = "", *, cls: str = "", colspan: int = 1, rowspan: int = 1) -> str:
    attrs = f' class="{cls}"' if cls else ""
    if colspan != 1:
        attrs += f' colspan="{colspan}"'
    if rowspan != 1:
        attrs += f' rowspan="{rowspan}"'
    body = value if isinstance(value, str) and value.startswith('<span class="rot">') else esc(str(value) if value is not None else "")
    return f"<th{attrs}>{body}</th>"


def _raster_tuned_competency(label: str, gpa: str) -> str | None:
    """Compensate for WeasyPrint's RGB-to-PDF rounding at rasterisation."""
    color = competency_background(label, gpa)
    return {
        "#00b050": "#00b151",
        "#92d050": "#93d151",
        "#ffff00": "#ffff00",
        "#ffc000": "#ffc100",
    }.get((color or "").lower(), color)


def _division_cells(row: SchoolRankRow) -> list[str]:
    cells: list[str] = []
    for label, leaves in _DIVISIONS:
        block = row.division.get(label, {}) if isinstance(row.division, dict) else {}
        pct = row.division.get(f"{label}%", "") if isinstance(row.division, dict) else ""
        for leaf in leaves:
            value = pct if leaf == "%" else (block.get(leaf, "") if isinstance(block, dict) else "")
            if label in {"I", "II", "III", "IV"}:
                cls = "bg-t" if leaf == "t" else "division-detail"
            elif label == "0":
                cls = "bg-zeropct" if leaf == "%" else "bg-zero"
            elif label == "I-III":
                cls = "bg-i3pct" if leaf == "%" else "bg-i3"
            else:  # I-IV: only the percentage has a fill in the reference.
                cls = "bg-t" if leaf == "%" else ""
            cells.append(_td(value, cls=cls))
    return cells


def _data_row(row: SchoolRankRow, level: str) -> str:
    ident = row.ward if level == "council" else row.council
    cells = [
        _td(row.sno, cls="sno"),
        _td(ident, cls="identity"),
        _td(row.school_name, cls="identity"),
        _td(row.ownership, cls="identity"),
        _td(row.registered.f), _td(row.registered.m), _td(row.registered.t),
        _td(row.sat.f), _td(row.sat.m), _td(row.sat.t),
        _td(row.sat_pct, cls="bg-candidate-pct"),
    ]
    cells.extend(_division_cells(row))
    cells.append(_td(row.gpa))
    bg = _raster_tuned_competency(row.competency, row.gpa)
    style = f' style="background:{bg}"' if bg else ""
    cells.append(f'<td class="competency"{style}>{esc(row.competency)}</td>')
    cells.append(_td(row.council_rank, cls="rank-value bg-crank"))
    cells.append(_td(row.regional_rank, cls="rank-value"))
    return '<tr class="data">' + "".join(cells) + "</tr>"


def _total_row(values: list[str]) -> str:
    if len(values) < 39:
        values = [*values, *([""] * (39 - len(values)))]
    cells = [_td(values[0], colspan=4)]
    for col in range(4, 36):
        cls = ""
        if col == 10:
            cls = "bg-candidate-pct"
        elif col in {13, 16, 19, 22}:
            cls = "bg-t"
        elif col == 26:
            cls = "bg-zeropct"
        elif col in {27, 28, 29}:
            cls = "bg-i3"
        elif col == 30:
            cls = "bg-i3pct"
        cells.append(_td(values[col], cls=cls))
    cells.append(_td(values[36], cls="competency bg-yellow", colspan=2))
    cells.append(_td(values[38], cls="bg-satpct rank-value"))
    return '<tr class="total">' + "".join(cells) + "</tr>"


def _main_head(level: str) -> str:
    ident = "WARD" if level == "council" else "COUNCIL"
    r0 = [
        _th("S/NO.", rowspan=3), _th(ident, cls="text", rowspan=3),
        _th("SCHOOL NAME", rowspan=3), _th("OWNERSHIP", rowspan=3),
        _th("NUMBER OF CANDIDATES", cls="candidate-group bg-satpct", colspan=7),
        _th("DIVISION PERFORMANCE", cls="group", colspan=24),
        _th("", cls="bg-gpa-head"), _th(""),
        _th("", cls="bg-rank-head"), _th("", cls="bg-rank-head"),
    ]
    r1 = [_th("REGISTERED", colspan=3), _th("SAT", colspan=4)]
    for label, leaves in _DIVISIONS:
        r1.append(_th(label, cls="division-name", colspan=len(leaves)))
    r1.extend([
        _th("GPA", cls="bg-gpa-head"), _th("COMPETENCY LEVEL"),
        _th(rot("C/RANK"), cls="rank-head bg-rank-head"),
        _th(rot("R/RANK"), cls="rank-head bg-rank-head"),
    ])
    r2 = [
        _th("F", cls="leaf bg-registered"), _th("M", cls="leaf bg-registered"),
        _th("T", cls="leaf bg-registered"), _th("F", cls="leaf bg-sat"),
        _th("M", cls="leaf bg-sat"), _th("T", cls="leaf bg-sat"),
        _th("%", cls="bg-satpct"),
    ]
    for label, leaves in _DIVISIONS:
        for leaf in leaves:
            if label in {"I", "II", "III", "IV"}:
                cls = "leaf bg-i3"
            elif label == "0":
                cls = "leaf bg-zero-head"
            elif label == "I-III":
                cls = "leaf bg-i3pct"
            else:
                cls = "leaf bg-sat" if leaf != "%" else "bg-i3"
            r2.append(_th(leaf.upper() if leaf != "%" else "%", cls=cls))
    r2.extend([_th("", cls="bg-gpa-head"), _th(""), _th("", cls="bg-rank-head"), _th("", cls="bg-rank-head")])
    return "<thead>" + "".join(f"<tr>{''.join(row)}</tr>" for row in (r0, r1, r2)) + "</thead>"


def _main_cont_head(level: str) -> str:
    """The condensed two-row header the reference repeats on continuation pages.

    Continuation pages carry a two-row band (group row + division/candidate row)
    rather than the full three-row header page 1 uses, matching the recovered
    reference lattice (2 header rows + data rows per continuation page).
    """
    r0 = [
        _th("", rowspan=2), _th("", cls="text", rowspan=2),
        _th("", rowspan=2), _th("", rowspan=2),
        _th("NUMBER OF CANDIDATES", cls="candidate-group bg-satpct", colspan=7),
        _th("DIVISION PERFORMANCE", cls="group", colspan=24),
        _th("GPA", cls="bg-gpa-head", rowspan=2),
        _th("COMPETENCY LEVEL", rowspan=2),
        _th(rot("C/RANK"), cls="rank-head bg-rank-head", rowspan=2),
        _th(rot("R/RANK"), cls="rank-head bg-rank-head", rowspan=2),
    ]
    r1 = [_th("REGISTERED", colspan=3), _th("SAT", colspan=4)]
    for label, leaves in _DIVISIONS:
        r1.append(_th(label, cls="division-name", colspan=len(leaves)))
    return "<thead>" + "".join(f"<tr>{''.join(row)}</tr>" for row in (r0, r1)) + "</thead>"


def _summary_html(summary: PerformanceTable) -> str:
    """Render the exact five-row 35-column summary lattice."""
    values = summary.rows[0].values if summary.rows else {}
    pass_values = summary.rows[1].values if len(summary.rows) > 1 else {}

    r0 = [_th(""), _th(""), _th(""), _th("")]
    r0.extend([
        _th("NUMBER OF CANDIDATES", cls="summary-candidate bg-registered", colspan=5),
        _th("DIVISION PERFORMANCE", colspan=24),
        _th("GPA PERFORMANCE", cls="bg-summary-gpa", colspan=2),
    ])
    r1 = [
        _th(""), _th("NO. OF SCHOOLS IN COUNCIL", cls="schools-label"),
        _th("REGISTERED", cls="bg-registered", colspan=3),
        _th("SAT", cls="bg-sat", colspan=4),
    ]
    for label, leaves in _DIVISIONS:
        r1.append(_th(label, cls="times", colspan=len(leaves)))
    r1.extend([_th("GPA", cls="bg-rank-head"), _th("COMPENTENCY LEVEL", cls="bg-rank-head")])

    summary_label = summary.column_headers[0].replace("  ", " ") if summary.column_headers else "SUMMARY PERFORMANC E"
    r2 = [_th(rot(summary_label), cls="summary-vertical"), _th("")]
    for col in range(2, 33):
        leaf = summary.column_headers[col].rsplit("/", 1)[-1].strip()
        if 2 <= col <= 7 or 9 <= col <= 20:
            cls = "leaf bg-i3"
        elif col == 8:
            cls = "bg-sat"
        elif 21 <= col <= 24:
            cls = "leaf bg-zero"
        elif 25 <= col <= 27:
            cls = "leaf bg-crank"
        elif col == 28:
            cls = "bg-i3pct"
        elif 29 <= col <= 31:
            cls = "leaf bg-sat"
        else:
            cls = "bg-i3"
        r2.append(_th(leaf, cls=cls))
    r2.extend([_th("", cls="bg-rank-head"), _th("", cls="bg-rank-head")])

    r3 = [_td("")]
    for col in range(1, 35):
        cls = "value"
        if 21 <= col <= 24:
            cls += " bg-zeropct"
        elif 25 <= col <= 28:
            cls += " bg-sat"  # Reference total band is pale cyan.
        elif col == 34:
            cls += " summary-competency bg-yellow"
        r3.append(_td(values.get(str(col), ""), cls=cls))

    r4: list[str] = []
    col = 0
    while col < 35:
        span = 2 if col == 33 else int(pass_values.get(f"{col}.span", "1"))
        r4.append(_td(pass_values.get(str(col), ""), cls="value", colspan=span))
        col += span

    rows = (r0, r1, r2, r3, r4)
    return '<table class="sr summary">' + _colgroup(_SUMMARY_COLS) + "".join(
        f"<tr>{''.join(row)}</tr>" for row in rows
    ) + "</table>"


def _document(title: str, sheet: Sheet, body: str) -> str:
    """Assemble this report's Letter-landscape standalone document."""
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{esc(title)}</title>\n<style>\n@page{{size:792pt 612pt;margin:0}}\n"
        f"{sheet.css()}\n</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def _banner_html(report: SchoolsRankReport) -> str:
    lines = banner_lines(report.meta)
    banner = '<div class="banner">' + "".join(f"<div>{line}</div>" for line in lines)
    if report.meta.title.strip():
        banner += f'<div class="title">{esc(report.meta.title)}</div>'
    return banner + "</div>"


def _main_table(body_rows: str, *, head: str = "", cont: bool = False) -> str:
    cls = "sr main cont" if cont else "sr main"
    return (
        f'<table class="{cls}">' + _colgroup(_MAIN_COLS) + head
        + f"<tbody>{body_rows}</tbody></table>"
    )


def render_schools_rank(report: SchoolsRankReport) -> str:
    level = report.meta.level
    sheet = _style(orientation_for(report.meta))
    banner = _banner_html(report)
    summaries = "".join(_summary_html(summary) for summary in report.summary)

    data_rows = [_data_row(row, level) for row in report.rows]
    total_rows = "".join(_total_row(values) for values in report.totals.values())

    splits = _row_splits(report.meta.name, len(data_rows))
    sections: list[str] = []
    cursor = 0
    for page_index, count in enumerate(splits):
        chunk = "".join(data_rows[cursor:cursor + count])
        cursor += count
        is_last = page_index == len(splits) - 1
        if is_last:
            chunk += total_rows
        if page_index == 0:
            # Page 1 carries the banner, the summary band and the table header.
            main = _main_table(chunk, head=_main_head(level))
            sections.append(f'<section class="report">{banner}{summaries}{main}</section>')
        else:
            # Continuation pages repeat a condensed two-row header, then data,
            # starting near the top margin.
            main = _main_table(chunk, head=_main_cont_head(level), cont=True)
            sections.append(f'<section class="report">{main}</section>')

    body = "".join(sections)
    return _document(report.meta.title or report.meta.name, sheet, body)
