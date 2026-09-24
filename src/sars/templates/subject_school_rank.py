"""Fixed-layout single-subject school-rank report (portrait Letter).

Covers the region single-subject ranks (EDK 1 page, English 6 pages) and the
council subjectwise rank (24 pages, one grouped block per subject).  Each emits
its OWN portrait ``612pt 792pt`` page box and the reference page COUNT, replacing
the old A4 reflow.
"""

from __future__ import annotations

from ..schema import GenericTabularReport
from .base import banner_html
from .generic_fixed import (
    PORTRAIT,
    RenderedSection,
    _base_sheet,
    _document,
    _flatten_section,
    _page_section,
    _reconcile,
    _sections_of,
    _table_html,
)

# Recovered reference point sizes for the portrait single-subject ranks.
_BODY_PT = 6.0
_ROW_PT = 8.1
_BANNER_PT = 7.0

# Exact recovered per-page data-row split for the single-section variants, read
# from the reference PDFs so the page COUNT matches.  Uncatalogued reports fall
# back to a capacity-based split.
_SINGLE_SPLITS: dict[str, tuple[int, ...]] = {
    "Mwanza School Rank-EDK": (25,),
    "Mwanza School Rank-English Language": (62, 68, 68, 68, 68, 54),
}
_FIRST_PAGE_ROWS = 62
_CONT_PAGE_ROWS = 68

# The subjectwise report packs 18 grouped subject blocks onto 24 pages (plus one
# trailing blank page the reference pads to).  Each entry is one page: a list of
# ``(section_index, start_row, row_count)`` slices placed on that page, recovered
# from the reference PDF.  Big subjects span two pages; small trailing subjects
# share pages.
_SUBJECTWISE_PLAN: tuple[tuple[tuple[int, int, int], ...], ...] = (
    ((0, 0, 54),),
    ((0, 54, 11),),
    ((1, 0, 52),),
    ((1, 52, 13),),
    ((2, 0, 53),),
    ((2, 53, 12),),
    ((3, 0, 52),),
    ((3, 52, 13),),
    ((4, 0, 53),),
    ((4, 53, 12),),
    ((5, 0, 53),),
    ((5, 53, 11),),
    ((6, 0, 53),),
    ((6, 53, 11),),
    ((7, 0, 53),),
    ((7, 53, 11),),
    ((8, 0, 53),),
    ((8, 53, 12),),
    ((9, 0, 53),),
    ((9, 53, 11),),
    ((10, 0, 24), (11, 0, 9), (12, 0, 1)),
    ((12, 1, 13), (13, 0, 7), (14, 0, 13)),
    ((15, 0, 17), (16, 0, 4), (17, 0, 4)),
    (),  # trailing blank page the reference pads to.
)


def _is_subjectwise(report: GenericTabularReport) -> bool:
    return report.meta.variant == "subjectwise" or len(_sections_of(report)) > 1


def _render_single(report: GenericTabularReport) -> str:
    sections = _sections_of(report)
    rs = _flatten_section(sections[0])
    split = _SINGLE_SPLITS.get(report.meta.name)
    if split is None:
        total = len(rs.body_rows)
        counts = [min(_FIRST_PAGE_ROWS, total)]
        remaining = total - counts[0]
        while remaining > 0:
            take = min(_CONT_PAGE_ROWS, remaining)
            counts.append(take)
            remaining -= take
        split = tuple(counts)
    counts = _reconcile(list(split), len(rs.body_rows))

    sheet = _base_sheet(_BODY_PT, _ROW_PT, _BANNER_PT)
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
    return _document(report.meta.title or report.meta.name, PORTRAIT, sheet, "".join(pages))


def _plan_for(rendered: list[RenderedSection]) -> tuple[tuple[tuple[int, int, int], ...], ...]:
    """The subjectwise page plan, reconciled with the actual section sizes.

    Falls back to a fresh-page-per-section capacity split when the catalogued
    plan does not line up (e.g. an uncatalogued subjectwise report), never
    dropping a row.
    """
    total_expected = sum(c for page in _SUBJECTWISE_PLAN for _, _, c in page)
    total_actual = sum(len(rs.body_rows) for rs in rendered)
    if len(rendered) == 18 and total_expected == total_actual:
        return _SUBJECTWISE_PLAN
    # Capacity fallback: each section starts a new page and flows onward.
    plan: list[tuple[tuple[int, int, int], ...]] = []
    for si, rs in enumerate(rendered):
        n = len(rs.body_rows)
        if n == 0:
            plan.append(((si, 0, 0),))
            continue
        start = 0
        first = True
        while start < n:
            cap = _FIRST_PAGE_ROWS if first else _CONT_PAGE_ROWS
            take = min(cap, n - start)
            plan.append(((si, start, take),))
            start += take
            first = False
    return tuple(plan)


def _render_subjectwise(report: GenericTabularReport) -> str:
    sections = _sections_of(report)
    rendered = [_flatten_section(s) for s in sections]
    plan = _plan_for(rendered)

    sheet = _base_sheet(_BODY_PT, _ROW_PT, _BANNER_PT)
    banner = banner_html(report.meta)

    pages: list[str] = []
    for pi, page_slices in enumerate(plan):
        inner = banner if pi == 0 else ""
        if not page_slices:
            pages.append(_page_section(inner))
            continue
        for si, start, count in page_slices:
            rs = rendered[si]
            chunk = "".join(rs.body_rows[start : start + count])
            # Attach the section's TOTAL rows to its final slice.
            if start + count >= len(rs.body_rows):
                chunk += "".join(rs.total_rows)
            inner += _table_html(rs, chunk, repeat_head=True)
        pages.append(_page_section(inner))
    return _document(report.meta.title or report.meta.name, PORTRAIT, sheet, "".join(pages))


def render_subject_school_rank(report: GenericTabularReport) -> str:
    """Render a single-subject school-rank report to a standalone portrait doc."""
    if _is_subjectwise(report):
        return _render_subjectwise(report)
    return _render_single(report)
