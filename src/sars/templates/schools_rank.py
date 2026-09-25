"""Schools-rank reports — each document's own recovered fixed layout.

Four documents rank schools this way (the council sheet and the region's overall
and government sheets), and each keeps its OWN layout spec under
``layouts/<report>.json``: its own page count, its own 39-column lattice, its own
division washes, its own summary band. Nothing is shared between them but this
module's plumbing, which only feeds data into whichever spec the report names.
"""

from __future__ import annotations

from ..layout_spec import binding_provider, render_html, resolve
from ..schema import SchoolsRankReport


def render_schools_rank(
    report: SchoolsRankReport,
    engine: str | None = None,
    *,
    grow: bool = False,
) -> str:
    """Render this report from its own recovered layout plus the given data."""
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
