"""Top-ten-schools reports — each document's own recovered fixed layout.

The council and region top-ten sheets each carry their own per-block headings
(``OVERALL`` / ``PRIVATE`` / ``GOVERNMENT``) as recovered chrome and their own
lattice, in ``layouts/<report>.json``; this module supplies the ranked rows.
"""

from __future__ import annotations

from ...layout_spec import binding_provider, render_html, resolve
from ...schema import SchoolsRankReport


def render_top_schools(
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
