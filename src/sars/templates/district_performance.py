"""Fixed-layout district-performance report (landscape Letter, 5 pages).

The reference prints one titled section per page (overall, government, private,
by-percentage, by-KPI).  Emits its OWN landscape ``792pt 612pt`` page box and one
page per section, so the page COUNT matches the reference exactly.
"""

from __future__ import annotations

from ..schema import GenericTabularReport
from .generic_fixed import LANDSCAPE, render_section_per_page

_BODY_PT = 5.2
_ROW_PT = 8.6
_BANNER_PT = 7.5


def render_district_performance(report: GenericTabularReport) -> str:
    """Render district performance as one landscape page per section."""
    return render_section_per_page(
        report,
        LANDSCAPE,
        body_pt=_BODY_PT,
        row_pt=_ROW_PT,
        banner_pt=_BANNER_PT,
        banner_on_first_only=False,
    )
