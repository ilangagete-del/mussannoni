"""Region district-performance report — recovered fixed layout, filled from data.

The district sheet is its own document: a landscape page whose bands rank every
council in the region. Its geometry, fills, fonts and row pitch live in
``layouts/Mwanza f2 District Performance.json``, recovered from its reference
PDF; this module supplies the data only.
"""

from __future__ import annotations

from ..layout_spec import binding_provider, has_spec, render_html
from ..schema import GenericTabularReport


def render_district_performance(report: GenericTabularReport, engine: str | None = None) -> str:
    """Render the district-performance report from its own recovered layout."""
    name = report.meta.name
    if not has_spec(name):  # pragma: no cover - the spec ships with the repo
        raise RuntimeError(
            f"{name!r} has no recovered layout spec; run tools/build_layout_specs.py"
        )
    return render_html(
        name,
        binding_provider(name, report),
        title=report.meta.title or name,
        engine=engine,
    )
