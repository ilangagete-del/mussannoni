"""Fixed-layout, self-contained best-students (overall) report.

Serves the ``best_students`` report type in its *overall* variant, at council
and region level: candidates ranked overall (and by female / male / ownership),
each block a titled section printing the same candidate columns.

Like :mod:`sars.templates.schools_rank` and :mod:`sars.templates.subjects_rank`
this renderer is deliberately independent from every other report family: its
page box, coordinates, table lattice, fonts, fills, row pitch, banner placement
and pagination are owned HERE and reproduce the reference layout at the
reference's own US-Letter page size (792 x 612 pt) and its true page COUNT,
instead of reflowing to A4.

Pagination mirrors the reference exactly: one titled section per page, except
the council report, which packs two sections onto each page.  No candidate row
is dropped - the row pitch is expressed as ``line-height`` on the cells (the
technique documented in the README) so WeasyPrint never discards a row that
would overflow an explicit ``tr`` height.

DATA IS DATA: the candidate rows are data; the per-column washes are this report
type's fixed chrome, authored here.  ``render_best_students`` dispatches to the
subjectwise renderer when ``meta.variant == "subjectwise"``.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..schema import BestStudentsReport, BestStudentsSection, StudentRow
from .base import banner_lines, orientation_for
from .best_students_subjectwise import render_best_students_subjectwise
from .styling import Sheet, esc, rot

#: Candidate columns as ``(field, heading, left_aligned, wash)``.  A column is
#: printed only when some candidate in the *report* fills it (present-column
#: detection), matching the reference (the council report prints no S/NO. or
#: COUNCIL column, the region report prints both).
_COLUMNS: tuple[tuple[str, str, bool, str], ...] = (
    ("sno", "S/NO.", False, ""),
    ("council", "COUNCIL", True, ""),
    ("cno", "C/NO", False, "cno"),
    ("school_name", "SCHOOL NAME", True, ""),
    ("name", "CANDIDATE FULL NAME", True, ""),
    ("sex", "SEX", False, "sex"),
    ("aggregate", "AGGT", False, "aggt"),
    ("division", "DIVISION", False, "division"),
    ("position", "POS", False, "pos"),
    ("detailed_subjects", "DETAILED SUBJECTS", True, "detail"),
)


@dataclass(frozen=True)
class _Theme:
    """Everything that varies between the council and region overall report."""

    #: Table origin x and the top of the table on page 1 / continuation pages.
    table_x: float
    table_top_p1: float
    table_top_cont: float
    #: The banner masthead font size and per-line baseline tops (page 1).
    banner_size: float
    banner_tops: tuple[float, ...]
    #: The section-title font size and its top on page 1 / continuation pages.
    title_size: float
    title_top_p1: float
    title_top_cont: float
    #: Recovered header-row height and data-row pitch (pt).
    header_height: float
    row_height: float
    #: Header / data font sizes (pt).
    head_size: float
    data_size: float
    detail_size: float
    #: True when the reference repeats the masthead on every page (region).
    banner_every_page: bool
    #: How many titled sections the reference packs onto one page.
    sections_per_page: int
    #: Per-column washes keyed by the column ``wash`` id.
    fills: dict[str, str]
    #: A wash painted behind the whole table (the region report's pale yellow).
    table_bg: str = ""
    #: The wash on the POSITION column's body cells (council uses pale yellow).
    pos_data_fill: str = ""
    #: The heading used for the position column (``POSITION`` vs ``POS``).
    pos_heading: str = "POS"


_COUNCIL = _Theme(
    table_x=18.32,
    table_top_p1=130.67,
    table_top_cont=96.11,
    banner_size=7.8,
    banner_tops=(57.8, 70.0, 82.2, 94.5),
    title_size=7.8,
    title_top_p1=114.8,
    title_top_cont=78.4,
    header_height=39.41,
    row_height=12.24,
    head_size=6.8,
    data_size=6.8,
    detail_size=6.8,
    banner_every_page=False,
    sections_per_page=2,
    pos_heading="POSITION",
    pos_data_fill="#ffffcc",
    fills={
        "cno": "#ffffcc",
        "sex": "#f2f2f2",
        "aggt": "#daeef3",
        "division": "#daeef3",
        "pos": "#fde9d9",
        "detail": "",
    },
)

_REGION = _Theme(
    table_x=18.38,
    table_top_p1=119.51,
    table_top_cont=119.51,
    banner_size=7.0,
    banner_tops=(56.9, 67.4, 77.8, 88.2),
    title_size=7.8,
    title_top_p1=104.3,
    title_top_cont=104.3,
    header_height=33.74,
    row_height=12.6,
    head_size=6.0,
    data_size=6.0,
    detail_size=7.0,
    banner_every_page=True,
    sections_per_page=1,
    pos_heading="POS",
    table_bg="#ffffcc",
    fills={
        "cno": "",
        "sex": "#fbe2d5",
        "aggt": "",
        "division": "#c1f0c8",
        "pos": "#fbe2d5",
        "detail": "#ffffcc",
    },
)


def _theme_for(report: BestStudentsReport) -> _Theme:
    return _REGION if report.meta.level == "region" else _COUNCIL


def _present_columns(
    sections: list[BestStudentsSection],
) -> tuple[tuple[str, str, bool, str], ...]:
    """Columns some candidate in the whole report fills (present-column rule)."""
    students = [st for sec in sections for st in sec.students]
    return tuple(
        col
        for col in _COLUMNS
        if any(str(getattr(st, col[0], "") or "").strip() for st in students)
    )


def _column_widths(theme: _Theme, columns: tuple[tuple[str, str, bool, str], ...]) -> list[float]:
    """Recovered column widths (pt) for the present columns.

    Widths are recovered per report; the flexible ``DETAILED SUBJECTS`` column
    absorbs the remaining table width so the lattice always spans the recovered
    table box exactly.
    """
    # Recovered fixed widths keyed by column field; the detail column flexes.
    fixed = (
        {
            "cno": 48.64,
            "school_name": 69.38,
            "name": 128.19,
            "sex": 20.64,
            "aggregate": 21.6,
            "division": 21.6,
            "position": 21.6,
        }
        if theme is _COUNCIL
        else {
            "sno": 24.22,
            "council": 50.16,
            "cno": 46.08,
            "school_name": 72.12,
            "name": 114.72,
            "sex": 19.56,
            "aggregate": 20.4,
            "division": 20.4,
            "position": 20.4,
        }
    )
    total_width = 749.73 if theme is _COUNCIL else 758.41
    widths: list[float] = []
    detail_index = None
    used = 0.0
    for i, (field_name, *_rest) in enumerate(columns):
        if field_name == "detailed_subjects":
            detail_index = i
            widths.append(0.0)
        else:
            w = fixed.get(field_name, 30.0)
            widths.append(w)
            used += w
    if detail_index is not None:
        widths[detail_index] = max(total_width - used, 60.0)
    return widths


# --------------------------------------------------------------------------- #
# Style
# --------------------------------------------------------------------------- #
def _style(theme: _Theme) -> Sheet:
    sheet = Sheet()
    banner_rules = "".join(
        f".banner .l{i}{{top:{top:.2f}pt}}" for i, top in enumerate(theme.banner_tops)
    )
    # Row pitch as line-height (rule width deducted) so no row is dropped.
    data_lh = theme.row_height - 0.4
    font_stack = 'Arial,"Liberation Sans",Helvetica,sans-serif'
    # Each rule is emitted on ONE physical line: the Sheet accumulator splits on
    # newlines and dedups, so a rule broken across lines that shares a line with
    # another rule would be silently truncated.
    rules = [
        "html,body{margin:0;padding:0;width:792pt;height:612pt;background:#fff}",
        f"body{{color:#000;font-family:{font_stack}}}",
        ".report{position:relative;width:792pt;height:612pt;overflow:hidden}",
        ".report + .report{page-break-before:always}",
        f".banner div{{position:absolute;left:0;width:792pt;text-align:center;font-weight:700;font-family:{font_stack};font-size:{theme.banner_size:.2f}pt;line-height:1}}",
        banner_rules,
        f".title{{position:absolute;left:0;width:792pt;text-align:center;font-weight:700;font-family:{font_stack};font-size:{theme.title_size:.2f}pt;line-height:1}}",
        "table.bs{position:absolute;border-collapse:collapse;table-layout:fixed;border-spacing:0;margin:0;padding:0}",
        "table.bs col{box-sizing:border-box}",
        f"table.bs th,table.bs td{{box-sizing:border-box;border:0.4pt solid #000;padding:0 1pt;text-align:center;vertical-align:middle;overflow:hidden;white-space:nowrap;font-family:{font_stack};color:#000;line-height:1}}",
        f"table.bs th{{font-weight:700;font-size:{theme.head_size:.2f}pt;white-space:normal;line-height:1}}",
        ".rot{display:inline-block;transform:rotate(-90deg);transform-origin:50% 50%;white-space:nowrap;line-height:1}",
        f"table.bs td{{font-weight:400;font-size:{theme.data_size:.2f}pt;line-height:{data_lh:.3f}pt}}",
        "table.bs th.text{text-align:left}",
        "table.bs td.text{text-align:left;padding-left:4pt;padding-right:2.5pt}",
        f"table.bs td.detail{{text-align:left;font-size:{theme.detail_size:.2f}pt;padding-left:4pt;padding-right:2.5pt}}",
        f"table.bs thead tr{{height:{theme.header_height:.3f}pt}}",
        f"table.bs tr.section-title td{{height:{theme.header_height:.3f}pt;white-space:normal;overflow:hidden}}",
        f"table.bs tr.inner-head{{height:{theme.header_height:.3f}pt}}",
        f"table.bs tr.inner-head th{{font-weight:700;font-size:{theme.head_size:.2f}pt;white-space:normal;line-height:1}}",
        f".bg-cno{{background:{theme.fills.get('cno') or 'transparent'}}}",
        f".bg-sex{{background:{theme.fills.get('sex') or 'transparent'}}}",
        f".bg-aggt{{background:{theme.fills.get('aggt') or 'transparent'}}}",
        f".bg-division{{background:{theme.fills.get('division') or 'transparent'}}}",
        f".bg-pos{{background:{theme.fills.get('pos') or 'transparent'}}}",
        f".bg-detail{{background:{theme.fills.get('detail') or 'transparent'}}}",
        f".bg-posdata{{background:{theme.pos_data_fill or 'transparent'}}}",
    ]
    sheet.extend("\n".join(rules))
    return sheet


def _colgroup(widths: list[float]) -> str:
    return "<colgroup>" + "".join(f'<col style="width:{w:.3f}pt">' for w in widths) + "</colgroup>"


def _head_cells(
    theme: _Theme,
    columns: tuple[tuple[str, str, bool, str], ...],
    widths: list[float],
) -> str:
    cells: list[str] = []
    for i, (field_name, heading, left, wash) in enumerate(columns):
        label = theme.pos_heading if field_name == "position" else heading
        cls_parts = []
        if left:
            cls_parts.append("text")
        if wash and theme.fills.get(wash):
            cls_parts.append(f"bg-{wash}")
        cls = f' class="{" ".join(cls_parts)}"' if cls_parts else ""
        # A single-word caption that is wider than a narrow column is printed
        # rotated in the reference (one glyph wide); keep it as one span so it
        # stays a single token and reproduces the reference lattice.
        rotate = (
            not left
            and " " not in label
            and widths[i] < 30.0
            and len(label) * theme.head_size * 0.62 > widths[i]
        )
        body = rot(esc(label)) if rotate else esc(label)
        cells.append(f"<th{cls}>{body}</th>")
    return "".join(cells)


def _head(
    theme: _Theme,
    columns: tuple[tuple[str, str, bool, str], ...],
    widths: list[float],
) -> str:
    return f'<thead><tr>{_head_cells(theme, columns, widths)}</tr></thead>'


def _fit_style(value: str, width: float, base_size: float) -> str:
    """Inline font-size that keeps *value* on one line inside a *width* cell.

    The reference condenses long names / detailed-subject strings to fit their
    fixed column instead of clipping them; reproduce that so every glyph stays
    inside its cell (no clipping, no bleeding into the neighbour) and no value
    is lost.  Arial averages ~0.52em per glyph; ``1.6pt`` covers the cell
    padding and borders.
    """
    text = value.strip()
    if not text:
        return ""
    usable = max(width - 12.0, 1.0)
    needed = len(text) * base_size * 0.62
    if needed <= usable:
        return ""
    size = max(usable / (len(text) * 0.62), 3.0)
    return f"font-size:{size:.2f}pt"


def _data_row(
    theme: _Theme,
    columns: tuple[tuple[str, str, bool, str], ...],
    widths: list[float],
    st: StudentRow,
) -> str:
    cells: list[str] = []
    for i, (field_name, _heading, left, _wash) in enumerate(columns):
        value = str(getattr(st, field_name, "") or "")
        cls_parts = []
        base = theme.detail_size if field_name == "detailed_subjects" else theme.data_size
        if field_name == "detailed_subjects":
            cls_parts.append("detail")
        elif left:
            cls_parts.append("text")
        if field_name == "position" and theme.pos_data_fill:
            cls_parts.append("bg-posdata")
        cls = f' class="{" ".join(cls_parts)}"' if cls_parts else ""
        # Condense long text to fit its fixed column (see _fit_style).
        style = ""
        if left or field_name == "detailed_subjects":
            fit = _fit_style(value, widths[i], base)
            style = f' style="{fit}"' if fit else ""
        cells.append(f"<td{cls}{style}>{esc(value)}</td>")
    return "<tr>" + "".join(cells) + "</tr>"


# --------------------------------------------------------------------------- #
# Document assembly
# --------------------------------------------------------------------------- #
def _banner_spans(theme: _Theme, report: BestStudentsReport) -> str:
    lines = banner_lines(report.meta)
    spans: list[str] = []
    for i, line in enumerate(lines):
        idx = min(i, len(theme.banner_tops) - 1)
        spans.append(f'<div class="l{idx}">{line}</div>')
    return '<div class="banner">' + "".join(spans) + "</div>"


def _inner_title_row(theme: _Theme, text: str, ncols: int) -> str:
    """A full-width section-title row printed inside the table.

    The council reference stacks two sections in one ruled table, separating
    them with a full-width title row; reproduce that lattice so the recovered
    table structure (one table per page) matches.
    """
    return (
        f'<tr class="section-title"><td colspan="{ncols}" '
        f'style="text-align:center;font-weight:700;font-size:{theme.title_size:.2f}pt">'
        f"{esc(text)}</td></tr>"
    )


def _page_table(
    theme: _Theme,
    columns: tuple[tuple[str, str, bool, str], ...],
    widths: list[float],
    page_sections: list[BestStudentsSection],
    top: float,
) -> str:
    """One ruled table for every section placed on the page.

    The first section's caption is drawn as a positioned title above the table;
    each subsequent section is introduced by a full-width title row and a
    repeated column header, matching the reference's single-table-per-page
    lattice.
    """
    head = _head(theme, columns, widths)
    ncols = len(columns)
    rows: list[str] = []
    for si, section in enumerate(page_sections):
        if si > 0:
            rows.append(_inner_title_row(theme, section.title, ncols))
            rows.append(f'<tr class="inner-head">{_head_cells(theme, columns, widths)}</tr>')
        rows.append("".join(_data_row(theme, columns, widths, st) for st in section.students))
    bg = f"background:{theme.table_bg};" if theme.table_bg else ""
    return (
        f'<table class="bs" style="left:{theme.table_x:.2f}pt;top:{top:.2f}pt;'
        f'width:{sum(widths):.3f}pt;{bg}">'
        + _colgroup(widths)
        + head
        + f'<tbody>{"".join(rows)}</tbody></table>'
    )


def _title_html(text: str, size: float, top: float) -> str:
    if not text.strip():
        return ""
    return f'<div class="title" style="top:{top:.2f}pt;font-size:{size:.2f}pt">{esc(text)}</div>'


def _document(title: str, sheet: Sheet, body: str) -> str:
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{esc(title)}</title>\n<style>\n@page{{size:792pt 612pt;margin:0}}\n"
        f"{sheet.css()}\n</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def render_best_students(report: BestStudentsReport) -> str:
    """Render a :class:`~sars.schema.BestStudentsReport` to a standalone doc.

    Dispatches to the subjectwise renderer for a subjectwise list.
    """
    if (report.meta.variant or "").lower() == "subjectwise":
        return render_best_students_subjectwise(report)

    orientation_for(report.meta)  # landscape by design
    theme = _theme_for(report)
    sheet = _style(theme)

    sections = [sec for sec in report.sections if sec.students]
    columns = _present_columns(sections)
    widths = _column_widths(theme, columns)

    banner = _banner_spans(theme, report)

    # Pack sections onto pages exactly as the reference does.
    per_page = max(theme.sections_per_page, 1)
    pages: list[list[BestStudentsSection]] = [
        sections[i : i + per_page] for i in range(0, len(sections), per_page)
    ] or [[]]

    html_pages: list[str] = []
    for page_index, page_sections in enumerate(pages):
        first = page_index == 0
        parts: list[str] = []
        banner_here = first or theme.banner_every_page
        if banner_here:
            parts.append(banner)
        base_title_top = theme.title_top_p1 if banner_here else theme.title_top_cont
        base_table_top = theme.table_top_p1 if banner_here else theme.table_top_cont
        # The first section's caption sits above the single per-page table.
        if page_sections:
            title = page_sections[0].title
            parts.append(_title_html(title, theme.title_size, base_title_top))
            parts.append(_page_table(theme, columns, widths, page_sections, base_table_top))
        html_pages.append(f'<section class="report">{"".join(parts)}</section>')

    return _document(report.meta.title or report.meta.name, sheet, "".join(html_pages))
