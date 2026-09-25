"""Mock-mobility report — recovered fixed layout, filled from data.

The mobility sheet compares each school's movement between assessments, and it
is drawn nothing like the other reports: its own portrait page box, its own
bespoke per-cell tints, its own fonts (it is the one document that uses Arial
Italic). All of that is recovered into ``layouts/Mwanza f2 Mock Mobility
2026.json``; this module supplies the data only.
"""

from __future__ import annotations

from ..layout_spec import binding_provider, render_html, resolve
from ..schema import GenericTabularReport


def render_mock_mobility(
    report: GenericTabularReport,
    engine: str | None = None,
    *,
    grow: bool = False,
) -> str:
    """Render the mock-mobility report from its own recovered layout."""
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
