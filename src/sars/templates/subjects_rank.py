"""Fixed-layout, self-contained subjects-rank report.

Serves the ``subjects_rank`` report type (council and region level): subjects
ranked by their grade breakdown and GPA.  Like :mod:`sars.templates.schools_rank`
this renderer is deliberately independent from every other report family - its
page box, coordinates, table lattice, fonts, fills, spans and row pitches are
owned HERE and reproduce the reference layout at the reference's own US-Letter
page size (792 x 612 pt) and its true page COUNT (two pages for both known
reports), instead of reflowing to A4.

DATA IS DATA: the counts / GPA / rank are data; the per-column washes are this
report type's fixed chrome, authored here; the competency band colour is the
only data-derived colour, computed deterministically (:mod:`sars.competency`).

Expected data shape: a :class:`~sars.schema.SubjectsRankReport`.  The extraction
folds the two aggregate lines (``OVERALL SUBJECTS ... GPA`` and
``COMPETENCY LEVEL``) into ``report.rows`` as pseudo rows whose value lives in
``grades['A']``; this renderer detects and lays them out as the reference's
full-width summary band.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..schema import SubjectRankRow, SubjectsRankReport
from .base import banner_lines, competency_background, orientation_for
from .styling import Sheet, esc, rot

#: Grade / summary columns in printed order (logical columns 2..11).
_GRADE_COLS: tuple[str, ...] = ("A", "B", "C", "D", "F", "TOTAL", "A-C", "%A-C", "A-D", "%A-D")


@dataclass(frozen=True)
class _Theme:
    """Everything that varies between the council and region subjects-rank."""

    #: Table origin (x, top) in points for page 1 and page 2.
    p1_origin: tuple[float, float]
    p2_origin: tuple[float, float]
    #: Recovered column widths (15 columns) for page 1 and page 2.
    p1_cols: tuple[float, ...]
    p2_cols: tuple[float, ...]
    #: Header row heights (two rows), data-row height, summary-row heights.
    header_heights: tuple[float, float]
    data_height: float
    #: (gpa row height, competency row height, trailing empty row height).
    summary_heights: tuple[float, float, float]
    #: How many data rows sit on page 1 (the rest, plus the summary band and a
    #: trailing empty row, go on page 2).  Read from the reference PDFs.
    page1_rows: int
    #: True when the reference repeats the two-row header on page 2.
    repeat_header_p2: bool
    #: Banner line font size (pt) and the recovered baseline tops per line.
    banner_size: float
    banner_tops: tuple[float, ...]
    #: Header / data / summary font sizes (pt).
    head_group_size: float   # "GRADE PERFORMANCE" and leaf-grade letters
    head_leaf_size: float    # S/NO., SUBJECT NAME, TOTAL, GPA, ... captions
    data_size: float         # numeric grade / gpa cells
    ident_size: float        # sno / subject-name / competency / rank cells
    summary_value_size: float
    #: Per-cell fill washes keyed by role.
    fills: dict[str, str]


# ---- Recovered reference geometry ---------------------------------------- #
# All measured with sars.extract.extract_document on the reference PDFs.

_COUNCIL = _Theme(
    p1_origin=(34.38, 146.54),
    p2_origin=(34.36, 54.45),
    p1_cols=(36.60, 144.16, 38.17, 31.92, 31.92, 31.89, 39.17, 36.676, 36.524,
             36.60, 36.60, 36.66, 40.048, 122.642, 27.431),
    p2_cols=(36.62, 143.80, 38.53, 31.92, 31.92, 31.89, 39.18, 36.56, 36.63,
             36.60, 36.60, 36.60, 40.108, 122.769, 27.177),
    header_heights=(14.872, 26.195),
    data_height=18.240,
    summary_heights=(20.583, 20.856, 16.656),
    page1_rows=20,
    repeat_header_p2=False,
    banner_size=11.6,
    banner_tops=(57.77, 75.17, 92.57, 109.25, 128.09),
    head_group_size=11.6,
    head_leaf_size=10.0,
    data_size=10.8,
    ident_size=10.0,
    summary_value_size=11.6,
    fills={
        "head_f": "#ff0000",
        "head_total": "#ebf1de",
        "head_ac": "#65ffab",
        "head_ad": "#daeef3",
        "head_gpa": "#d8e4bc",
        "head_comp": "",
        "head_rank": "#fde9d9",
        "data_f": "#fcd5b4",
        "data_ac": "#65ffab",
        "data_ad": "#d2fce6",
        "data_gpa": "#ffffcc",
        "data_rank": "#f2f2f2",
    },
)

_REGION = _Theme(
    p1_origin=(34.60, 132.56),
    p2_origin=(34.54, 54.74),
    p1_cols=(33.92, 215.486, 30.634, 30.84, 33.12, 33.127, 33.20, 33.083, 33.071,
             30.892, 33.068, 30.916, 35.256, 94.32, 25.422),
    p2_cols=(33.984, 215.378, 30.742, 30.84, 33.12, 33.135, 33.15, 33.168, 33.027,
             30.876, 33.084, 30.93, 35.23, 94.393, 25.382),
    header_heights=(15.141, 23.782),
    data_height=15.480,
    summary_heights=(17.364, 17.592, 14.184),
    page1_rows=24,
    repeat_header_p2=True,
    banner_size=10.1,
    banner_tops=(56.98, 71.74, 86.50, 100.66, 116.74),
    head_group_size=10.1,
    head_leaf_size=8.7,
    data_size=9.4,
    ident_size=8.7,
    summary_value_size=10.1,
    fills={
        "head_f": "#f1a983",
        "head_total": "#c1f0c8",
        "head_ac": "#65ffab",
        "head_ad": "#f2ceef",
        "head_gpa": "#83e28e",
        "head_comp": "#ffffcc",
        "head_rank": "#daf2d0",
        "head_abcd": "#f2f2f2",
        "data_f": "#fbe2d5",
        "data_ac": "#65ffab",
        "data_ad": "#d2fce6",
        "data_gpa": "#ffffcc",
        "data_rank": "#f2f2f2",
    },
)


def _theme_for(report: SubjectsRankReport) -> _Theme:
    return _REGION if report.meta.level == "region" else _COUNCIL


def _caption(labels: list[str], canonical: str, *aliases: str) -> str:
    """The report's own caption for a column, falling back to *canonical*."""
    wanted = {canonical.upper(), *(a.upper() for a in aliases)}
    for label in labels:
        if label and label.upper() in wanted:
            return label
    return canonical


def _is_summary_row(row: SubjectRankRow) -> bool:
    """True for the aggregate ``... GPA`` / ``COMPETENCY LEVEL`` pseudo rows.

    The extractor stores these with the aggregate label in ``sno`` and the value
    in ``grades['A']`` (there is no real subject name).
    """
    return not row.subject_name and bool(row.sno) and not row.rank


# --------------------------------------------------------------------------- #
# Style
# --------------------------------------------------------------------------- #
def _style(theme: _Theme) -> Sheet:
    sheet = Sheet()
    fills = theme.fills
    banner_rules = "".join(
        f".banner .l{i}{{top:{top:.2f}pt}}" for i, top in enumerate(theme.banner_tops)
    )
    abcd = fills.get("head_abcd", "")
    abcd_rule = f".sj th.abcd{{background:{abcd}}}" if abcd else ""
    comp_head = fills.get("head_comp", "")
    comp_head_rule = f".sj th.comp-head{{background:{comp_head}}}" if comp_head else ""
    sheet.extend(f"""
html,body{{margin:0;padding:0;width:792pt;height:612pt;background:#fff}}
body{{color:#000;font-family:Arial,"Liberation Sans",Helvetica,sans-serif}}
.report{{position:relative;width:792pt;height:612pt;overflow:hidden}}
.report + .report{{page-break-before:always}}
.banner div{{position:absolute;left:0;width:792pt;text-align:center;font-weight:700;
        font-family:Arial,"Liberation Sans",Helvetica,sans-serif;
        font-size:{theme.banner_size:.2f}pt;line-height:1}}
{banner_rules}
table.sj{{position:absolute;border-collapse:collapse;table-layout:fixed;
        border-spacing:0;margin:0;padding:0}}
table.sj col{{box-sizing:border-box}}
table.sj th,table.sj td{{box-sizing:border-box;border:0.4pt solid #000;padding:0 0.6pt;
        text-align:center;vertical-align:middle;overflow:hidden;white-space:nowrap;
        font-family:Arial,"Liberation Sans",Helvetica,sans-serif;color:#000;line-height:1}}
table.sj .text{{text-align:left}}
table.sj thead th{{font-weight:700;font-size:{theme.head_leaf_size:.2f}pt}}
table.sj th.group{{font-size:{theme.head_group_size:.2f}pt}}
table.sj th.narrow{{font-family:"Arial Narrow","Nimbus Sans Narrow",Arial,sans-serif}}
table.sj td.data{{font-size:{theme.data_size:.2f}pt;font-weight:700}}
table.sj td.plain{{font-size:{theme.data_size:.2f}pt;font-weight:400}}
table.sj td.sno{{font-size:{theme.ident_size:.2f}pt;font-weight:400}}
table.sj td.subject{{font-size:{theme.ident_size:.2f}pt;font-weight:400;text-align:left}}
table.sj td.competency{{font-size:{theme.ident_size:.2f}pt;font-weight:700;text-align:left}}
table.sj td.rank{{font-size:{theme.ident_size:.2f}pt;font-weight:700}}
table.sj td.summary-label{{font-size:{theme.ident_size:.2f}pt;font-weight:700}}
table.sj td.summary-value{{font-size:{theme.summary_value_size:.2f}pt;font-weight:700}}
.rot{{display:inline-block;transform:rotate(-90deg);transform-origin:50% 50%;
      white-space:nowrap;line-height:1}}
{abcd_rule}
{comp_head_rule}
.bg-head-f{{background:{fills['head_f']}}}
.bg-head-total{{background:{fills['head_total']}}}
.bg-head-ac{{background:{fills['head_ac']}}}
.bg-head-ad{{background:{fills['head_ad']}}}
.bg-head-gpa{{background:{fills['head_gpa']}}}
.bg-head-rank{{background:{fills['head_rank']}}}
.bg-data-f{{background:{fills['data_f']}}}
.bg-data-ac{{background:{fills['data_ac']}}}
.bg-data-ad{{background:{fills['data_ad']}}}
.bg-data-gpa{{background:{fills['data_gpa']}}}
.bg-data-rank{{background:{fills['data_rank']}}}
""")
    # Table positions and per-row heights per page.
    h0, h1 = theme.header_heights
    sh_gpa, sh_comp, sh_empty = theme.summary_heights
    sheet.extend(f"""
table.p1{{left:{theme.p1_origin[0]:.2f}pt;top:{theme.p1_origin[1]:.2f}pt;width:{sum(theme.p1_cols):.3f}pt}}
table.p2{{left:{theme.p2_origin[0]:.2f}pt;top:{theme.p2_origin[1]:.2f}pt;width:{sum(theme.p2_cols):.3f}pt}}
table.sj thead tr:nth-child(1){{height:{h0:.3f}pt}}
table.sj thead tr:nth-child(2){{height:{h1:.3f}pt}}
table.sj tbody tr.data-row{{height:{theme.data_height:.3f}pt}}
table.sj tbody tr.sum-gpa{{height:{sh_gpa:.3f}pt}}
table.sj tbody tr.sum-comp{{height:{sh_comp:.3f}pt}}
table.sj tbody tr.sum-empty{{height:{sh_empty:.3f}pt}}
""")
    return sheet


def _colgroup(widths: tuple[float, ...]) -> str:
    return "<colgroup>" + "".join(f'<col style="width:{w:.3f}pt">' for w in widths) + "</colgroup>"


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
def _thead(theme: _Theme, labels: list[str]) -> str:
    fills = theme.fills
    comp_head_cls = "comp-head" if fills.get("head_comp") else ""
    comp_head_top = f'<th class="{comp_head_cls}">&#160;</th>' if comp_head_cls else '<th>&#160;</th>'
    # Row 0: S/NO. and SUBJECT NAME span both header rows; GRADE PERFORMANCE
    # groups the ten grade columns; the GPA / COMPETENCY / RANK columns have an
    # empty top half (rowspan=1) exactly as the reference lattice records.
    r0 = (
        '<th rowspan="2">S/NO.</th>'
        '<th rowspan="2">SUBJECT NAME</th>'
        f'<th class="group" colspan="{len(_GRADE_COLS)}">GRADE PERFORMANCE</th>'
        f'<th class="bg-head-gpa">&#160;</th>'
        f'{comp_head_top}'
        f'<th class="bg-head-rank">&#160;</th>'
    )
    # Row 1: grade leaf letters + the GPA / COMPETENCY LEVEL / RANK captions.
    abcd_cls = " abcd" if fills.get("head_abcd") else ""
    comp_leaf_cls = " comp-head" if comp_head_cls else ""
    r1_parts = [
        f'<th class="group{abcd_cls}">A</th>',
        f'<th class="group{abcd_cls}">B</th>',
        f'<th class="group{abcd_cls}">C</th>',
        f'<th class="group{abcd_cls}">D</th>',
        '<th class="group bg-head-f">F</th>',
        '<th class="narrow bg-head-total">TOTAL</th>',
        '<th class="bg-head-ac">A-C</th>',
        '<th class="bg-head-ac">%A-C</th>',
        '<th class="bg-head-ad">A-D</th>',
        '<th class="bg-head-ad">%A-D</th>',
        '<th class="bg-head-gpa">GPA</th>',
        f'<th class="narrow{comp_leaf_cls}">'
        f'{esc(_caption(labels, "COMPETENCY LEVEL", "COMPENTENCY LEVEL"))}</th>',
        f'<th class="narrow bg-head-rank">{rot(esc(_caption(labels, "RANK", "R/RANK", "C/RANK")))}</th>',
    ]
    return f'<thead><tr>{r0}</tr><tr>{"".join(r1_parts)}</tr></thead>'


# --------------------------------------------------------------------------- #
# Rows
# --------------------------------------------------------------------------- #
def _data_row(theme: _Theme, row: SubjectRankRow) -> str:
    fills = theme.fills
    grade_cls = {
        "F": "data bg-data-f",
        "A-C": "data bg-data-ac",
        "%A-C": "data bg-data-ac",
        "A-D": "data bg-data-ad",
        "%A-D": "data bg-data-ad",
    }
    cells = [
        f'<td class="sno">{esc(row.sno)}</td>',
        f'<td class="subject">{esc(row.subject_name)}</td>',
    ]
    for g in _GRADE_COLS:
        cls = grade_cls.get(g, "data" if g in {"TOTAL"} else "plain")
        cells.append(f'<td class="{cls}">{esc(row.grades.get(g, ""))}</td>')
    cells.append(f'<td class="data bg-data-gpa">{esc(row.gpa)}</td>')
    bg = competency_background(row.competency, row.gpa)
    style = f' style="background:{bg}"' if bg else ""
    cells.append(f'<td class="competency"{style}>{esc(row.competency)}</td>')
    cells.append(f'<td class="rank bg-data-rank">{esc(row.rank)}</td>')
    return '<tr class="data-row">' + "".join(cells) + "</tr>"


def _summary_rows(theme: _Theme, rows: list[SubjectRankRow]) -> str:
    """Render the aggregate GPA / competency band + a trailing empty row.

    Mirrors the reference lattice: each aggregate row is ``S/NO.`` label
    (colspan=2) + value (colspan=12) + an empty RANK cell (colspan=1); the final
    row is a single full-width (colspan=15) empty rule.
    """
    out: list[str] = []
    for i, row in enumerate(rows):
        value = row.grades.get("A", "")
        label_align = "right"
        cls = "sum-gpa" if i == 0 else "sum-comp"
        bg = ""
        if i == 1:  # the competency band carries the derived colour.
            colour = competency_background(value)
            bg = f' style="background:{colour}"' if colour else ""
        out.append(
            f'<tr class="{cls}">'
            f'<td class="summary-label" colspan="2" style="text-align:{label_align}">{esc(row.sno)}</td>'
            f'<td class="summary-value" colspan="12"{bg}>{esc(value)}</td>'
            f'<td colspan="1">&#160;</td>'
            "</tr>"
        )
    out.append('<tr class="sum-empty"><td colspan="15">&#160;</td></tr>')
    return "".join(out)


# --------------------------------------------------------------------------- #
# Document assembly
# --------------------------------------------------------------------------- #
def _banner_html(theme: _Theme, report: SubjectsRankReport) -> str:
    lines = banner_lines(report.meta)
    if report.meta.title.strip():
        lines.append(esc(report.meta.title))
    # Only lay out as many lines as we have recovered baseline tops for; extras
    # (rare) fall back onto the last recorded top so nothing is dropped.
    spans: list[str] = []
    for i, line in enumerate(lines):
        idx = min(i, len(theme.banner_tops) - 1)
        spans.append(f'<div class="l{idx}">{line}</div>')
    return '<div class="banner">' + "".join(spans) + "</div>"


def _table(cols: tuple[float, ...], page_cls: str, head: str, body: str) -> str:
    return (
        f'<table class="sj {page_cls}">' + _colgroup(cols) + head
        + f"<tbody>{body}</tbody></table>"
    )


def _document(title: str, sheet: Sheet, body: str) -> str:
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{esc(title)}</title>\n<style>\n@page{{size:792pt 612pt;margin:0}}\n"
        f"{sheet.css()}\n</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def render_subjects_rank(report: SubjectsRankReport) -> str:
    """Render a :class:`~sars.schema.SubjectsRankReport` to a standalone doc."""
    orientation_for(report.meta)  # validates orientation; landscape by design.
    theme = _theme_for(report)
    sheet = _style(theme)

    subjects = [r for r in report.rows if not _is_summary_row(r)]
    summary = [r for r in report.rows if _is_summary_row(r)]

    head = _thead(theme, report.column_headers)

    # Page 1: banner + full header + the first chunk of subject rows.
    p1_subjects = subjects[: theme.page1_rows]
    p1_body = "".join(_data_row(theme, r) for r in p1_subjects)
    p1_table = _table(theme.p1_cols, "p1", head, p1_body)
    banner = _banner_html(theme, report)
    sections = [f'<section class="report">{banner}{p1_table}</section>']

    # Page 2: (optionally) the repeated header, remaining subjects, then the
    # aggregate GPA / competency band and a trailing empty rule.
    p2_subjects = subjects[theme.page1_rows :]
    p2_body = "".join(_data_row(theme, r) for r in p2_subjects)
    p2_body += _summary_rows(theme, summary)
    p2_head = head if theme.repeat_header_p2 else ""
    p2_table = _table(theme.p2_cols, "p2", p2_head, p2_body)
    sections.append(f'<section class="report">{p2_table}</section>')

    return _document(report.meta.title or report.meta.name, sheet, "".join(sections))
