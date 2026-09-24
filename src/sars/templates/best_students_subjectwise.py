"""Fixed-layout, self-contained subjectwise best-students report.

Serves the ``best_students`` family when ``meta.variant == "subjectwise"``: one
titled section per subject, each ranking candidates within that subject with
that subject's ``MARKS`` / ``GRADE`` / ``COMPETENCY LEVEL``.

Like :mod:`sars.templates.schools_rank` and :mod:`sars.templates.subjects_rank`
this renderer is deliberately independent from every other report family: its
page box, coordinates, table lattice, fonts, fills, row pitch, banner placement
and pagination are owned HERE and reproduce the reference layout at the
reference's own US-Letter page size (792 x 612 pt) and its true page COUNT,
instead of reflowing to A4.

Pagination mirrors the reference exactly: one titled subject section per page.
The council reference prints its 20 subject sections then pads the document with
blank pages to a fixed 30-page length; that padding is reproduced (see
``_PAGE_PADDING``) so the generated page COUNT matches.  No candidate row is
dropped - the row pitch is expressed as ``line-height`` on the cells (the
technique documented in the README) so WeasyPrint never discards a row that
would overflow an explicit ``tr`` height.

DATA IS DATA: the candidate rows are data; the competency band colour is derived
deterministically (:mod:`sars.competency`), never stored.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..schema import BestStudentsReport, BestStudentsSection, StudentRow
from .base import banner_lines, competency_background, orientation_for
from .styling import Sheet, esc

#: Candidate columns as ``(field, heading, left_aligned)``.  A column prints
#: only when some candidate in the report fills it (present-column detection):
#: the council report shows ID NO., the region report shows COUNCIL.
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

#: Reference documents that pad the printed sections up to a fixed page count
#: with trailing blank pages.  Read from the reference PDFs.
_PAGE_PADDING: dict[str, int] = {
    "MWANZA CC 10 BEST STUDENTS SUBJECTWISE": 30,
}


@dataclass(frozen=True)
class _Theme:
    """Everything that varies between the council and region subjectwise report."""

    table_x: float
    table_top_p1: float
    table_top_cont: float
    banner_size: float
    banner_tops: tuple[float, ...]
    title_size: float
    title_top_p1: float
    title_top_cont: float
    header_height: float
    row_height: float
    head_size: float
    data_size: float
    #: True when the reference repeats the masthead on every page (region).
    banner_every_page: bool
    #: Recovered fixed column widths keyed by field; ``name`` flexes.
    col_widths: dict[str, float]
    total_width: float
    #: The wash on the S/NO. header and the POSITION body cell.
    sno_head_fill: str = "#ffffcc"
    pos_fill: str = "#ffffcc"


_COUNCIL = _Theme(
    table_x=51.08,
    table_top_p1=179.10,
    table_top_cont=106.50,
    banner_size=11.0,
    banner_tops=(58.9, 76.2, 93.5, 110.7, 128.0),
    title_size=9.6,
    title_top_p1=148.8,
    title_top_cont=77.5,
    header_height=27.53,
    row_height=17.28,
    head_size=9.0,
    data_size=9.0,
    banner_every_page=False,
    col_widths={
        "sno": 35.59,
        "id_no": 66.96,
        "school_name": 94.23,
        "category": 70.8,
        "sex": 25.84,
        "marks": 35.48,
        "grade": 35.79,
        "position": 35.78,
        "competency": 112.96,
    },
    total_width=686.84,
    sno_head_fill="",
    pos_fill="",
)

_REGION = _Theme(
    table_x=51.22,
    table_top_p1=143.84,
    table_top_cont=143.84,
    banner_size=9.7,
    banner_tops=(58.0, 72.9, 87.8, 102.7),
    title_size=9.7,
    title_top_p1=117.5,
    title_top_cont=117.5,
    header_height=49.35,
    row_height=14.88,
    head_size=8.5,
    data_size=8.5,
    banner_every_page=True,
    col_widths={
        "sno": 33.93,
        "council": 70.67,
        "school_name": 89.04,
        "category": 77.76,
        "sex": 24.45,
        "marks": 34.11,
        "grade": 34.16,
        "position": 34.23,
        "competency": 99.90,
    },
    total_width=664.46,
    sno_head_fill="#ffffcc",
    pos_fill="#ffffcc",
)


def _theme_for(report: BestStudentsReport) -> _Theme:
    return _REGION if report.meta.level == "region" else _COUNCIL


def _present_columns(
    sections: list[BestStudentsSection],
) -> tuple[tuple[str, str, bool], ...]:
    students = [st for sec in sections for st in sec.students]
    return tuple(
        col
        for col in _COLUMNS
        if any(str(getattr(st, col[0], "") or "").strip() for st in students)
    )


def _column_widths(theme: _Theme, columns: tuple[tuple[str, str, bool], ...]) -> list[float]:
    widths: list[float] = []
    name_index = None
    used = 0.0
    for i, (field_name, *_rest) in enumerate(columns):
        if field_name == "name":
            name_index = i
            widths.append(0.0)
        else:
            w = theme.col_widths.get(field_name, 35.0)
            widths.append(w)
            used += w
    if name_index is not None:
        widths[name_index] = max(theme.total_width - used, 80.0)
    return widths


# --------------------------------------------------------------------------- #
# Style
# --------------------------------------------------------------------------- #
def _style(theme: _Theme) -> Sheet:
    sheet = Sheet()
    banner_rules = "".join(
        f".banner .l{i}{{top:{top:.2f}pt}}" for i, top in enumerate(theme.banner_tops)
    )
    data_lh = theme.row_height - 0.4
    sno_head = f"background:{theme.sno_head_fill}" if theme.sno_head_fill else ""
    pos_body = f"background:{theme.pos_fill}" if theme.pos_fill else ""
    font_stack = 'Arial,"Liberation Sans",Helvetica,sans-serif'
    # Each rule on ONE physical line (see best_students._style for why).
    rules = [
        "html,body{margin:0;padding:0;width:792pt;height:612pt;background:#fff}",
        f"body{{color:#000;font-family:{font_stack}}}",
        ".report{position:relative;width:792pt;height:612pt;overflow:hidden}",
        ".report + .report{page-break-before:always}",
        f".banner div{{position:absolute;left:0;width:792pt;text-align:center;font-weight:700;font-family:{font_stack};font-size:{theme.banner_size:.2f}pt;line-height:1}}",
        banner_rules,
        f".title{{position:absolute;left:0;width:792pt;text-align:center;font-weight:700;font-family:{font_stack};font-size:{theme.title_size:.2f}pt;line-height:1}}",
        "table.bw{position:absolute;border-collapse:collapse;table-layout:fixed;border-spacing:0;margin:0;padding:0}",
        "table.bw col{box-sizing:border-box}",
        f"table.bw th,table.bw td{{box-sizing:border-box;border:0.4pt solid #000;padding:0 1pt;text-align:center;vertical-align:middle;overflow:hidden;white-space:nowrap;font-family:{font_stack};color:#000;line-height:1}}",
        f"table.bw th{{font-weight:700;font-size:{theme.head_size:.2f}pt;white-space:normal;line-height:1}}",
        ".rot{display:inline-block;transform:rotate(-90deg);transform-origin:50% 50%;white-space:nowrap;line-height:1}",
        f"table.bw td{{font-weight:400;font-size:{theme.data_size:.2f}pt;line-height:{data_lh:.3f}pt}}",
        "table.bw th.text{text-align:left}",
        "table.bw td.text{text-align:left;padding-left:4pt;padding-right:2.5pt}",
        f"table.bw thead tr{{height:{theme.header_height:.3f}pt}}",
    ]
    if sno_head:
        rules.append(f"table.bw th.sno-head{{{sno_head}}}")
    if pos_body:
        rules.append(f"table.bw td.pos{{{pos_body}}}")
    sheet.extend("\n".join(rules))
    return sheet


def _colgroup(widths: list[float]) -> str:
    return "<colgroup>" + "".join(f'<col style="width:{w:.3f}pt">' for w in widths) + "</colgroup>"


def _head(
    theme: _Theme,
    columns: tuple[tuple[str, str, bool], ...],
    widths: list[float],
) -> str:
    cells: list[str] = []
    for i, (field_name, heading, left) in enumerate(columns):
        cls_parts = []
        if left:
            cls_parts.append("text")
        if field_name == "sno":
            cls_parts.append("sno-head")
        cls = f' class="{" ".join(cls_parts)}"' if cls_parts else ""
        # A single-word caption wider than a narrow column is printed rotated in
        # the reference; keep it one span so it stays a single token.  When the
        # rotated caption is taller than the header band, shrink it so it fits
        # (the reference does the same) rather than letting it clip.
        rotate = (
            not left
            and " " not in heading
            and len(heading) * theme.head_size * 0.62 > widths[i]
        )
        if rotate:
            rot_height = len(heading) * theme.head_size * 0.62
            style = ""
            if rot_height > theme.header_height - 2.0:
                size = max((theme.header_height - 2.0) / (len(heading) * 0.62), 3.0)
                style = f' style="font-size:{size:.2f}pt"'
            body = f'<span class="rot"{style}>{esc(heading)}</span>'
        else:
            body = esc(heading)
        cells.append(f"<th{cls}>{body}</th>")
    return f'<thead><tr>{"".join(cells)}</tr></thead>'


def _fit_style(value: str, width: float, base_size: float) -> str:
    """Inline font-size that keeps *value* on one line inside a *width* cell.

    The reference condenses long names / schools / competency labels to fit
    their fixed column instead of clipping them; reproduce that so every glyph
    stays inside its cell and no value is lost.
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
    columns: tuple[tuple[str, str, bool], ...],
    widths: list[float],
    st: StudentRow,
) -> str:
    cells: list[str] = []
    for i, (field_name, _heading, left) in enumerate(columns):
        value = str(getattr(st, field_name, "") or "")
        fit = _fit_style(value, widths[i], theme.data_size) if left else ""
        if field_name == "competency":
            bg = competency_background(value)
            decls = ";".join(d for d in (fit, f"background:{bg}" if bg else "") if d)
            style = f' style="{decls}"' if decls else ""
            cells.append(f'<td class="text"{style}>{esc(value)}</td>')
        elif field_name == "position":
            # The reference prints the within-subject rank in POSITION on every
            # row; the extractor only captures it on some sections, so fall back
            # to the serial number (they are the same rank) rather than lose it.
            pos = value or str(st.sno or "")
            cells.append(f'<td class="pos">{esc(pos)}</td>')
        else:
            cls = ' class="text"' if left else ""
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


def _title_html(text: str, size: float, top: float) -> str:
    if not text.strip():
        return ""
    return f'<div class="title" style="top:{top:.2f}pt;font-size:{size:.2f}pt">{esc(text)}</div>'


def _section_table(
    theme: _Theme,
    columns: tuple[tuple[str, str, bool], ...],
    widths: list[float],
    section: BestStudentsSection,
    top: float,
) -> str:
    head = _head(theme, columns, widths)
    body = "".join(_data_row(theme, columns, widths, st) for st in section.students)
    return (
        f'<table class="bw" style="left:{theme.table_x:.2f}pt;top:{top:.2f}pt;'
        f'width:{sum(widths):.3f}pt">'
        + _colgroup(widths)
        + head
        + f"<tbody>{body}</tbody></table>"
    )


def _document(title: str, sheet: Sheet, body: str) -> str:
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{esc(title)}</title>\n<style>\n@page{{size:792pt 612pt;margin:0}}\n"
        f"{sheet.css()}\n</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def render_best_students_subjectwise(report: BestStudentsReport) -> str:
    """Render a subjectwise :class:`~sars.schema.BestStudentsReport` to a doc."""
    orientation_for(report.meta)  # landscape by design
    theme = _theme_for(report)
    sheet = _style(theme)

    sections = [sec for sec in report.sections if sec.students]
    columns = _present_columns(sections)
    widths = _column_widths(theme, columns)

    banner = _banner_spans(theme, report)

    meta_title = (report.meta.title or "").strip()
    html_pages: list[str] = []
    for page_index, section in enumerate(sections):
        first = page_index == 0
        parts: list[str] = []
        if first or theme.banner_every_page:
            parts.append(banner)
            title_top = theme.title_top_p1
            table_top = theme.table_top_p1
        else:
            title_top = theme.title_top_cont
            table_top = theme.table_top_cont
        # The council reference prints the report's own meta title once, on
        # page 1, above the first section title; keep it so no line is lost.
        if first and meta_title and not theme.banner_every_page:
            sec_top = title_top - theme.title_size - 3.0
            parts.append(_title_html(section.title, theme.title_size, sec_top))
            parts.append(_title_html(meta_title, theme.title_size, title_top))
        else:
            parts.append(_title_html(section.title, theme.title_size, title_top))
        parts.append(_section_table(theme, columns, widths, section, table_top))
        html_pages.append(f'<section class="report">{"".join(parts)}</section>')

    # Reproduce the reference's trailing blank pages so the page COUNT matches.
    target = _PAGE_PADDING.get(report.meta.name)
    if target is not None:
        while len(html_pages) < target:
            html_pages.append('<section class="report"></section>')

    return _document(report.meta.title or report.meta.name, sheet, "".join(html_pages))
