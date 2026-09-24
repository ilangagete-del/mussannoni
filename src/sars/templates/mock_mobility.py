"""Fixed-layout mock-mobility report (portrait Letter, 6 pages).

Emits its OWN portrait ``612pt 792pt`` page box and paginates the single ranked
section across the reference's 6 pages.  The reference draws the banner on page
one only; continuation pages carry the ranked table starting near the top.
"""

from __future__ import annotations

from ..schema import GenericTabularReport
from .generic_fixed import PORTRAIT, render_paginated_single_section

_BODY_PT = 6.4
_ROW_PT = 10.8
_BANNER_PT = 7.5

# Exact recovered per-page data-row split from the reference (6 pages).
_PAGE_SPLIT: tuple[int, ...] = (53, 61, 61, 61, 61, 54)


def render_mock_mobility(report: GenericTabularReport) -> str:
    """Render mock mobility as a paginated single-section portrait doc."""
    return render_paginated_single_section(
        report,
        PORTRAIT,
        page_row_counts=_PAGE_SPLIT,
        body_pt=_BODY_PT,
        row_pt=_ROW_PT,
        banner_pt=_BANNER_PT,
    )
