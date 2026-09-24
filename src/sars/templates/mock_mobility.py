"""Mock-mobility report — recovered fixed layout, filled from data.

The mobility sheet compares each school's movement between assessments, and it
is drawn nothing like the other reports: its own portrait page box, its own
bespoke per-cell tints, its own fonts (it is the one document that uses Arial
Italic). All of that is recovered into ``layouts/Mwanza f2 Mock Mobility
2026.json``; this module supplies the data only.
"""

from __future__ import annotations

from ..layout_spec import binding_provider, has_spec, render_html
from ..schema import GenericTabularReport


def render_mock_mobility(report: GenericTabularReport, engine: str | None = None) -> str:
    """Render the mock-mobility report from its own recovered layout."""
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
