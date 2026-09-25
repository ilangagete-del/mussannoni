"""Region district-performance report — recovered fixed layout, filled from data.

The district sheet is its own document: a landscape page whose bands rank every
council in the region. Its geometry, fills, fonts and row pitch live in
``layouts/Mwanza f2 District Performance.json``, recovered from its reference
PDF; this module supplies the data only.
"""

from __future__ import annotations

from ...layout_spec import binding_provider, render_html, resolve
from ...schema import GenericTabularReport


def render_district_performance(
    report: GenericTabularReport,
    engine: str | None = None,
    *,
    grow: bool = False,
) -> str:
    """Render the district-performance report from its own recovered layout."""
    name = report.meta.name
    layout = resolve(
        name,
        report_type=report.meta.report_type,
        level=report.meta.level,
        variant=report.meta.variant,
    )
    return render_html(
        layout,
        binding_provider(layout, report),
        title=report.meta.title or name,
        engine=engine,
        grow=grow,
    )
