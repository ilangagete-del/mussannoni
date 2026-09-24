"""Fixed-layout core shared by the four generic-family report renderers.

The reports served here (single-subject school ranks, the wards pivot, district
performance and mock mobility) were previously reflowed onto A4 with the wrong
page box and the wrong page count.  This module rebuilds them the way
:mod:`sars.templates.schools_rank` rebuilds its family: each report emits its
OWN Letter page box (portrait ``612pt 792pt`` or landscape ``792pt 612pt``),
lays every table out inside a fixed-size ``.page`` section, and paginates to the
reference page COUNT so no page-size or page-count mismatch remains.

Per the project learning each report type gets its own thin renderer
(:mod:`sars.templates.subject_school_rank`, :mod:`~sars.templates.wards_rank`,
:mod:`~sars.templates.district_performance`, :mod:`~sars.templates.mock_mobility`);
they share only this layout MECHANISM, never a cross-report visual identity.

DATA IS DATA: nothing here reads presentation from the data.  The only
data-derived colour is the competency band (:mod:`sars.competency`); every other
fill is the report type's fixed chrome, keyed to the recovered column group.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ..schema import GenericTabularReport, TabularSection
from .base import banner_html, competency_background
from .styling import Sheet, esc

_COMPETENCY_KEYS = ("COMPETENCY LEVEL", "COMPENTENCY LEVEL", "COMPETENCY")


@dataclass(frozen=True)
class PageBox:
    """The report's own Letter page box, in points."""

    width: float
    height: float

    @property
    def css(self) -> str:
        return f"@page{{size:{self.width:g}pt {self.height:g}pt;margin:0}}"


#: The two Letter boxes every FEAT-005 report uses.
PORTRAIT = PageBox(612.0, 792.0)
LANDSCAPE = PageBox(792.0, 612.0)


def _thead(paths: list[str]) -> str:
    """Rebuild the grouped header band from per-column label paths.

    A shallow column (e.g. ``S/N`` in a two-deep band) is emitted once with a
    ``rowspan`` reaching the band's full depth - matching the reference lattice -
    rather than a label on the first row and a blank cell below it, which would
    mis-align the header against the reference cell-for-cell.
    """
    if not paths:
        return ""
    split = [p.split(" / ") if p else [""] for p in paths]
    depth = max(len(s) for s in split)
    real_len = [len(s) for s in split]
    padded = [s + [s[-1]] * (depth - len(s)) for s in split]
    n = len(padded)

    # ``emitted[r][c]`` marks a cell already covered by a rowspan/colspan above.
    covered = [[False] * n for _ in range(depth)]
    rows_html: list[str] = []
    for r in range(depth):
        cells: list[str] = []
        c = 0
        while c < n:
            if covered[r][c]:
                c += 1
                continue
            # Colspan: neighbours sharing the same path prefix at this depth.
            prefix = padded[c][: r + 1]
            colspan = 1
            while c + colspan < n and padded[c + colspan][: r + 1] == prefix and not covered[r][c + colspan]:
                colspan += 1
            # Rowspan: a leaf column (its real path ends at or before this row)
            # occupies every remaining header row.
            rowspan = 1
            if real_len[c] <= r + 1:
                rowspan = depth - r
            text = padded[c][r]
            attrs = ""
            if colspan > 1:
                attrs += f' colspan="{colspan}"'
            if rowspan > 1:
                attrs += f' rowspan="{rowspan}"'
            cells.append(f"<th{attrs}>{esc(text)}</th>")
            for rr in range(r, r + rowspan):
                for cc in range(c, c + colspan):
                    covered[rr][cc] = True
            c += colspan
        rows_html.append("<tr>" + "".join(cells) + "</tr>")
    return "".join(rows_html)


def _is_text_col(leaf: str) -> bool:
    up = leaf.upper()
    return any(k in up for k in ("NAME", "WARD", "COUNCIL", "SCHOOL", "SUBJECT", "DISTRICT"))


def _leaves(paths: list[str]) -> list[str]:
    return [p.split(" / ")[-1] if p else "" for p in paths]


def _body_row(
    values_by_key: dict[str, str],
    paths: list[str],
    leaves: list[str],
    comp_idx: int | None,
    gpa_idx: int | None,
    *,
    cls: str = "",
) -> str:
    cells: list[str] = []
    for i, path in enumerate(paths):
        leaf = leaves[i]
        value = values_by_key.get(path, values_by_key.get(leaf, ""))
        text_col = _is_text_col(leaf)
        if i == comp_idx:
            gpa = ""
            if gpa_idx is not None:
                gpa = values_by_key.get(paths[gpa_idx], values_by_key.get(leaves[gpa_idx], ""))
            bg = competency_background(value, gpa)
            style = f' style="background-color:{bg}"' if bg else ""
            cls_attr = ' class="text"' if text_col else ""
            cells.append(f"<td{cls_attr}{style}>{esc(value)}</td>")
        else:
            cls_attr = ' class="text"' if text_col else ""
            cells.append(f"<td{cls_attr}>{esc(value)}</td>")
    tr_cls = f' class="{cls}"' if cls else ""
    return f"<tr{tr_cls}>" + "".join(cells) + "</tr>"


@dataclass
class RenderedSection:
    """A section flattened into its header band and its body rows."""

    title: str
    paths: list[str]
    header_html: str
    body_rows: list[str]  # each a full <tr>...</tr>
    total_rows: list[str]  # each a full <tr class="total">...</tr>
    n_cols: int
    colgroup: str  # <colgroup> with proportional widths keyed to the leaf type


#: Relative column-width weights by leaf semantics.  Text columns (names) get a
#: wide share so long school / council / district names are not clipped (which
#: would drop them from the recovered text); numeric columns stay narrow.  These
#: are structure-derived layout weights, not stored presentation.
def _col_weight(leaf: str) -> float:
    up = leaf.upper()
    if "SCHOOL" in up:
        return 9.0
    if "NAME" in up:
        return 8.0
    if any(k in up for k in ("DISTRICT", "COUNCIL", "WARD")):
        return 6.0
    if "COMPETENCY" in up or "COMPENTENCY" in up:
        return 6.0
    if "OWNERSHIP" in up or "CATEGORY" in up:
        return 3.0
    if up in ("S/NO.", "S/NO", "SNO", "S/N", "S/N."):
        return 1.6
    if "GPA" in up:
        return 3.0
    if "RANK" in up:
        return 2.0
    if "HALI" in up or "MJONGEO" in up:
        return 3.4
    if "(" in up and "%" in up:
        return 3.2
    if up.startswith("%") or up.endswith("%"):
        return 2.4
    return 1.7


def _colgroup(paths: list[str]) -> str:
    leaves = _leaves(paths)
    weights = [_col_weight(leaf) for leaf in leaves]
    total = sum(weights) or 1.0
    cols = "".join(f'<col style="width:{w / total * 100:.3f}%">' for w in weights)
    return f"<colgroup>{cols}</colgroup>"


def _flatten_section(section: TabularSection) -> RenderedSection:
    paths = section.column_headers
    leaves = _leaves(paths)
    comp_idx = next(
        (i for i, leaf in enumerate(leaves) if leaf.upper() in _COMPETENCY_KEYS),
        None,
    )
    gpa_idx = next((i for i, leaf in enumerate(leaves) if leaf.upper() == "GPA"), None)

    body_rows = [
        _body_row(trow.values, paths, leaves, comp_idx, gpa_idx) for trow in section.rows
    ]
    total_rows: list[str] = []
    for _label, values in section.totals.items():
        cells = "".join(f"<td>{esc(v)}</td>" for v in values)
        total_rows.append(f'<tr class="total">{cells}</tr>')

    return RenderedSection(
        title=section.title,
        paths=paths,
        header_html=_thead(paths),
        body_rows=body_rows,
        total_rows=total_rows,
        n_cols=len(paths),
        colgroup=_colgroup(paths),
    )


def _sections_of(report: GenericTabularReport) -> list[TabularSection]:
    if report.sections:
        return list(report.sections)
    return [
        TabularSection(
            column_headers=report.column_headers,
            rows=report.rows,
            totals=report.totals,
        )
    ]


def _table_html(rs: RenderedSection, body: str, *, repeat_head: bool) -> str:
    title = (
        f'<div class="section-title">{esc(rs.title)}</div>' if rs.title else ""
    )
    head = f"<thead>{rs.header_html}</thead>" if repeat_head else ""
    return (
        title
        + '<table class="gt">'
        + rs.colgroup
        + head
        + f"<tbody>{body}</tbody>"
        + "</table>"
    )


def _page_section(inner: str) -> str:
    return f'<section class="page">{inner}</section>'


def _base_sheet(body_pt: float, row_pt: float, banner_pt: float) -> Sheet:
    """The shared print stylesheet, every rule on ONE physical line.

    (:class:`sars.templates.styling.Sheet.extend` dedups per line and drops a
    multi-line rule that shares a continuation line, so rules are kept inline.)
    """
    sheet = Sheet()
    sheet.add("html,body{margin:0;padding:0;background:#fff}")
    sheet.add("body{color:#000;font-family:Arial,\"Liberation Sans\",Helvetica,sans-serif}")
    sheet.add(".page{position:relative;overflow:hidden;box-sizing:border-box;padding:4pt 6pt}")
    sheet.add(".page + .page{page-break-before:always}")
    sheet.add(
        f".banner{{text-align:center;font-weight:700;font-size:{banner_pt:.2f}pt;line-height:1.35}}"
    )
    sheet.add(f".banner .title{{margin-top:4pt;font-size:{banner_pt:.2f}pt}}")
    sheet.add(
        f".section-title{{text-align:center;font-weight:700;font-size:{banner_pt:.2f}pt;"
        f"margin:4pt 0 2pt 0}}"
    )
    sheet.add(
        "table.gt{border-collapse:collapse;table-layout:fixed;width:100%;border-spacing:0;"
        "margin-top:4pt}"
    )
    sheet.add(
        f"table.gt th,table.gt td{{border:0.4pt solid #000;padding:0 0.6pt;text-align:center;"
        f"vertical-align:middle;overflow:visible;font-size:{body_pt:.2f}pt;"
        f"line-height:{row_pt:.2f}pt;white-space:nowrap}}"
    )
    sheet.add("table.gt th{font-weight:700;white-space:normal}")
    # Text columns (names) carry the long values; keep them on one line but let a
    # too-long value shrink to fit its box (via a smaller display) rather than be
    # clipped away - a clipped glyph is dropped from the recovered text.
    sheet.add(
        "table.gt td.text,table.gt th.text{text-align:left;overflow:hidden;"
        "text-overflow:clip}"
    )
    sheet.add("table.gt tr.total th,table.gt tr.total td{font-weight:700}")
    return sheet


def _document(title: str, box: PageBox, sheet: Sheet, body: str) -> str:
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{esc(title)}</title>\n<style>\n{box.css}\n{sheet.css()}\n</style>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )


def render_paginated_single_section(
    report: GenericTabularReport,
    box: PageBox,
    *,
    page_row_counts: Iterable[int],
    body_pt: float,
    row_pt: float,
    banner_pt: float,
) -> str:
    """Render a one-section report split across pages at ``page_row_counts``.

    Page 1 carries the masthead banner and the header band; continuation pages
    repeat the header band near the top margin.  ``page_row_counts`` is the exact
    per-page data-row split recovered from the reference so the page COUNT
    matches.  No row is ever dropped: any drift between the recovered split and
    the extracted rows is absorbed onto the last page.
    """
    sections = _sections_of(report)
    rs = _flatten_section(sections[0])
    counts = _reconcile(list(page_row_counts), len(rs.body_rows))

    sheet = _base_sheet(body_pt, row_pt, banner_pt)
    banner = banner_html(report.meta)

    pages: list[str] = []
    cursor = 0
    for pi, count in enumerate(counts):
        chunk = "".join(rs.body_rows[cursor : cursor + count])
        cursor += count
        if pi == len(counts) - 1:
            chunk += "".join(rs.total_rows)
        table = _table_html(rs, chunk, repeat_head=True)
        inner = (banner + table) if pi == 0 else table
        pages.append(_page_section(inner))

    body = "".join(pages)
    return _document(report.meta.title or report.meta.name, box, sheet, body)


def render_section_per_page(
    report: GenericTabularReport,
    box: PageBox,
    *,
    body_pt: float,
    row_pt: float,
    banner_pt: float,
    banner_on_first_only: bool = True,
) -> str:
    """Render a report whose reference prints one section per page.

    Used by district performance (5 sections -> 5 pages).  Each section carries
    its own header band, data rows and TOTAL row.
    """
    sections = _sections_of(report)
    rendered = [_flatten_section(s) for s in sections]

    sheet = _base_sheet(body_pt, row_pt, banner_pt)
    banner = banner_html(report.meta)

    pages: list[str] = []
    for pi, rs in enumerate(rendered):
        body_rows = "".join(rs.body_rows) + "".join(rs.total_rows)
        table = _table_html(rs, body_rows, repeat_head=True)
        show_banner = banner if (pi == 0 or not banner_on_first_only) else ""
        pages.append(_page_section(show_banner + table))

    body = "".join(pages)
    return _document(report.meta.title or report.meta.name, box, sheet, body)


def _reconcile(counts: list[int], total_rows: int) -> list[int]:
    """Fit a recovered per-page split to the actual row count without loss."""
    counts = [c for c in counts if c > 0] or [total_rows]
    placed = sum(counts)
    if placed < total_rows:
        counts[-1] += total_rows - placed
    elif placed > total_rows:
        overflow = placed - total_rows
        while overflow and counts:
            take = min(overflow, counts[-1])
            counts[-1] -= take
            overflow -= take
            if counts[-1] == 0 and len(counts) > 1:
                counts.pop()
    return [c for c in counts if c > 0] or [total_rows]
