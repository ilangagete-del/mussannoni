"""Fixed-layout wards-rank pivot report (landscape Letter, single page).

Emits its OWN landscape ``792pt 612pt`` page box and the reference single-page
layout: a small SUMMARY PERFORMANCE block followed by the ranked wards table.
"""

from __future__ import annotations

from ..schema import GenericTabularReport
from .base import banner_html
from .generic_fixed import (
    LANDSCAPE,
    _base_sheet,
    _document,
    _flatten_section,
    _page_section,
    _sections_of,
    _table_html,
)

_BODY_PT = 6.0
_ROW_PT = 8.5
_BANNER_PT = 7.5


def render_wards_rank(report: GenericTabularReport) -> str:
    """Render the wards-rank pivot to a standalone single-page landscape doc."""
    sections = _sections_of(report)
    sheet = _base_sheet(_BODY_PT, _ROW_PT, _BANNER_PT)
    banner = banner_html(report.meta)

    blocks = [banner]
    for s in sections:
        rs = _flatten_section(s)
        body = "".join(rs.body_rows) + "".join(rs.total_rows)
        blocks.append(_table_html(rs, body, repeat_head=True))

    body = _page_section("".join(blocks))
    return _document(report.meta.title or report.meta.name, LANDSCAPE, sheet, body)
