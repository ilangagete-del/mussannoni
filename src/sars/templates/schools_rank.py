"""Schools-rank reports — each document's own recovered fixed layout.

Four documents rank schools this way (the council sheet and the region's overall
and government sheets), and each keeps its OWN layout spec under
``layouts/<report>.json``: its own page count, its own 39-column lattice, its own
division washes, its own summary band. Nothing is shared between them but this
module's plumbing, which only feeds data into whichever spec the report names.
"""

from __future__ import annotations

from ..layout_spec import binding_provider, has_spec, render_html
from ..schema import SchoolsRankReport


def render_schools_rank(report: SchoolsRankReport, engine: str | None = None) -> str:
    """Render this report from its own recovered layout plus the given data."""
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
